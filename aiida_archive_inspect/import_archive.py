import json
import urllib.parse as urlparse
import ipywidgets as ipw
from aiida import profile_context, orm
from aiida.manage.configuration import get_config
from aiida.common.folders import SandboxFolder


class ImportArchive(ipw.VBox):
    def __init__(self, jupyter_notebook_url):
        super().__init__()
        self.url = urlparse.urlsplit(jupyter_notebook_url)
        self.query = urlparse.parse_qs(self.url.query)
        self.filename = self.query.get("file", [None])[0]
        self.record_id = self.query.get("record_id", [None])[0]
        self.profiles = get_config().profiles
        self.profile_names = [profile.name for profile in self.profiles]

        if not self.filename or not self.record_id:
            raise ValueError("URL must include file and record_id parameters")

        self.setup_widgets()

    def setup_widgets(self):
        self.profile_selector_description = ipw.HTML("<b>Select a profile:</b>")
        self.profile_selector = ipw.Dropdown(
            options=self.profile_names,
            description="",
            disabled=False,
        )

        self.import_button = ipw.Button(
            description="Import archive",
            disabled=False,
            button_style="primary",
            tooltip="Click to import the archive",
        )
        self.import_button.on_click(self.on_import_button_clicked)
        self.status = ipw.HTML("")
        self.open_notebook_button = ipw.HTML("")

        self.children = [
            self.profile_selector_description,
            self.profile_selector,
            self.import_button,
            self.status,
            self.open_notebook_button,
        ]

    def on_import_button_clicked(self, b):
        profile = self.profile_selector.value
        filename = self.filename
        record_id = self.record_id
        group_pk = self.exists_in_stored_archives(profile, filename, record_id)

        with profile_context(profile):
            if not group_pk:
                group_pk = self.import_mc_archive(filename, record_id)
                self.update_stored_archives(profile, filename, record_id, group_pk)
                self.status.value += (
                    f"<p>Archive imported as group with pk {group_pk}</p>"
                )
            else:
                self.status.value += (
                    f"<p>Archive already imported as group with pk {group_pk}</p>"
                )

            self.open_notebook_button.value += f"""
            <a href="/apps/apps/aiida-archive-inspect/overview.ipynb?group_pk={group_pk}&profile={profile}" target="_blank">
                <button>Inspect the archive</button>
            </a>
            """

    def update_stored_archives(self, profile, filename, record_id, group_pk):
        try:
            with open("stored_archives.json") as f:
                stored_archives = json.load(f)
        except FileNotFoundError:
            stored_archives = []

        stored_archives.append(
            {
                "Record id": record_id,
                "Filename": filename,
                "PK": group_pk,
                "Profile": profile,
            }
        )

        with open("stored_archives.json", "w") as f:
            json.dump(stored_archives, f, indent=4)

    def exists_in_stored_archives(self, profile, filename, record_id):
        try:
            with open("stored_archives.json") as f:
                stored_archives = json.load(f)
        except FileNotFoundError:
            return False

        for archive in stored_archives:
            if (
                archive["Record id"] == record_id
                and archive["Filename"] == filename
                and archive["Profile"] == profile
            ):
                return archive["PK"]
        return False

    def add_progress_bar(self, progress_bar, progress_text):
        """
        Dynamically add a progress bar and progress text to the widget layout.
        """
        # progress_container = ipw.VBox([progress_text, progress_bar])
        progress_container = ipw.VBox([progress_bar])
        # Temporarily store progress widgets to remove them later
        self.progress_widgets = progress_container
        # Update the class' children to include the progress widgets
        self.children = [
            self.profile_selector_description,
            self.profile_selector,
            self.import_button,
            self.progress_widgets,
            self.status,
            self.open_notebook_button,
        ]

    def download_with_progressbar(self, url, filename):
        import urllib.request

        # Initialize the progress bar widget
        progress_bar = ipw.FloatProgress(
            value=0.0,
            min=0.0,
            max=1.0,
            description="Downloading:",
            style={"bar_color": "#0074D9"},
        )
        progress_text = ipw.HTML("Preparing download...")
        # Dynamically add the progress bar to the class' display
        self.add_progress_bar(progress_bar, progress_text)

        # Open the URL to fetch headers and determine total size
        with urllib.request.urlopen(url) as response:
            try:
                total_size = int(response.getheader("Content-Length").strip())
                progress_bar.max = total_size  # Set the progress bar's max value
                progress_text.value = "Downloading..."
            except Exception:
                total_size = None
                progress_text.value = "Unknown filesize, downloading..."

        # Download with progress updates
        with urllib.request.urlopen(url) as response, open(filename, "wb") as out_file:
            if total_size is not None:
                downloaded = 0
                chunk_size = 4096
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    progress_bar.value = downloaded  # Update the progress bar
            else:
                # If Content-Length was not provided, just download the file without progress updates
                out_file.write(response.read())

        progress_text.value = "Download complete."

    def import_mc_archive(self, filename, record_id):
        mc_archive_base = (
            "https://archive.materialscloud.org/record/file?filename={}&record_id={}"
        )
        archive_file_url = mc_archive_base.format(filename, record_id)
        # Assuming running in a temporary sandbox folder context
        with SandboxFolder() as temp_folder:
            archive_path = temp_folder.get_abs_path("downloaded_archive.zip")
            self.download_with_progressbar(archive_file_url, archive_path)

            group_id = self.import_archive_and_migrate(archive_path, {}, True)
            if group_id:
                group = orm.load_group(group_id)
                group.base.extras.set("mc_record_id", record_id)
                group.base.extras.set("mc_filename", filename)
                return group_id
            else:
                return None

    def import_archive_and_migrate(self, archive, import_kwargs, try_migration):
        """Perform the archive import.

        :param archive: the path or URL to the archive
        :param web_based: If the archive needs to be downloaded first
        :param import_kwargs: keyword arguments to pass to the import function
        :param try_migration: whether to try a migration if the import raises `IncompatibleStorageSchema`

        """
        from aiida.common.folders import SandboxFolder
        from aiida.tools.archive.abstract import get_format
        from aiida.tools.archive.imports import import_archive as _import_archive
        from aiida.common.exceptions import IncompatibleStorageSchema

        archive_format = get_format()
        filepath = None
        group_id = None

        with SandboxFolder(filepath=filepath) as temp_folder:
            archive_path = archive

            self.status.value += "<p>Starting import...</p>"
            try:
                group_id = _import_archive(
                    archive_path, archive_format=archive_format, **import_kwargs
                )
                self.status.value += (
                    f"<p>Imported archive successfully as group with PK={group_id}.</p>"
                )
            except IncompatibleStorageSchema as exception:
                if try_migration:
                    self.status.value += (
                        "<p>Incompatible version detected, trying migration...</p>"
                    )
                    try:
                        new_path = temp_folder.get_abs_path("migrated_archive.aiida")
                        archive_format.migrate(
                            archive_path,
                            new_path,
                            archive_format.latest_version,
                            compression=0,
                        )
                        archive_path = new_path
                        self.status.value += "<p>Migration completed, proceeding with import of migrated archive.</p>"
                    except Exception as sub_exception:
                        self.status.value += f"<p>An exception occurred while migrating the archive: {sub_exception}</p>"
                        return

                    try:
                        group_id = _import_archive(
                            archive_path, archive_format=archive_format, **import_kwargs
                        )
                        self.status.value += f"<p>Imported migrated archive successfully as group with PK={group_id}.</p>"
                    except Exception as sub_exception:
                        self.status.value += f"<p>An exception occurred while trying to import the migrated archive: {sub_exception}</p>"
                else:
                    self.status.value += f"<p>An exception occurred while trying to import the archive: {exception}</p>"
            except Exception as exception:
                self.status.value += f"<p>An exception occurred while trying to import the archive: {exception}</p>"

        return group_id

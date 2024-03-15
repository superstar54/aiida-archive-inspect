import json
import urllib.parse as urlparse
import ipywidgets as ipw
from aiida import profile_context
from aiida_archive_inspect.utils import import_mc_archive
from aiida.manage.configuration import get_config


class ImportArchive(ipw.HBox):
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
        self.children = [
            self.widget_layout
        ]  # Set the children of the HBox to include the widget layout

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

        # VBox to organize the widgets vertically inside the HBox
        self.widget_layout = ipw.VBox(
            children=[
                self.profile_selector_description,
                self.profile_selector,
                self.import_button,
                self.status,
                self.open_notebook_button,
            ]
        )

    def on_import_button_clicked(self, b):
        profile = self.profile_selector.value
        filename = self.filename
        record_id = self.record_id
        group_pk = self.exists_in_stored_archives(profile, filename, record_id)

        with profile_context(profile):
            if not group_pk:
                group_pk = import_mc_archive(filename, record_id)
                self.update_stored_archives(profile, filename, record_id, group_pk)
                print(f"Archive imported as group with pk {group_pk}")
            else:
                self.status = ipw.HTML(
                    f"Archive already imported as group with pk {group_pk}"
                )

            self.open_notebook_button = ipw.HTML(
                f"""
            <a href="/notebooks/apps/aiida-archive-inspect/overview.ipynb?group_pk={group_pk}&profile={profile}" target="_blank">
                <button>Inspect the archive</button>
            </a>
            """
            )
            self.children = [
                ipw.VBox(
                    children=[
                        self.profile_selector_description,
                        self.profile_selector,
                        self.import_button,
                        self.status,
                        self.open_notebook_button,
                    ]
                )
            ]

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

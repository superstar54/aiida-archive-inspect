def import_archive_and_migrate(
    archive: str, web_based: bool, import_kwargs: dict, try_migration: bool
):
    """Perform the archive import.

    :param archive: the path or URL to the archive
    :param web_based: If the archive needs to be downloaded first
    :param import_kwargs: keyword arguments to pass to the import function
    :param try_migration: whether to try a migration if the import raises `IncompatibleStorageSchema`

    """
    import urllib.request

    from aiida.common.folders import SandboxFolder
    from aiida.tools.archive.abstract import get_format
    from aiida.tools.archive.imports import import_archive as _import_archive
    from aiida.common.exceptions import IncompatibleStorageSchema

    archive_format = get_format()
    filepath = None

    with SandboxFolder(filepath=filepath) as temp_folder:
        archive_path = archive

        if web_based:
            print(f"Downloading archive: {archive}")
            try:
                with urllib.request.urlopen(archive) as response:
                    temp_folder.create_file_from_filelike(
                        response, "downloaded_archive.zip"
                    )
            except Exception as exception:
                print(f"downloading archive failed", exception)

            archive_path = temp_folder.get_abs_path("downloaded_archive.zip")
            # print("archive downloaded, proceeding with import")

        print(f"Starting import:")
        try:
            group_id = _import_archive(
                archive_path, archive_format=archive_format, **import_kwargs
            )
        except IncompatibleStorageSchema as exception:
            if try_migration:
                print(f"    incompatible version detected for, trying migration")
                try:
                    new_path = temp_folder.get_abs_path("migrated_archive.aiida")
                    archive_format.migrate(
                        archive_path,
                        new_path,
                        archive_format.latest_version,
                        compression=0,
                    )
                    archive_path = new_path
                except Exception as sub_exception:
                    print(
                        f"    an exception occurred while migrating the archive",
                        sub_exception,
                    )

                print("    proceeding with import of migrated archive")
                try:
                    group_id = _import_archive(
                        archive_path, archive_format=archive_format, **import_kwargs
                    )
                except Exception as sub_exception:
                    print(
                        f"    an exception occurred while trying to import the migrated archive",
                        sub_exception,
                    )
            else:
                print(
                    f"    an exception occurred while trying to import the archive",
                    exception,
                )
        except Exception as exception:
            print(
                f"    an exception occurred while trying to import the archive",
                exception,
            )

        print(f"Imported archive successfully!")
        return group_id


def import_mc_archive(filename, record_id):
    from subprocess import run

    mc_archive_base = (
        "https://archive.materialscloud.org/record/file?filename={}&record_id={}"
    )

    archive_file_url = mc_archive_base.format(filename, record_id)

    def run_(*args, **kwargs):
        return run(*args, capture_output=True, check=True, **kwargs)

    group_id = import_archive_and_migrate(
        archive_file_url, web_based=True, import_kwargs={}, try_migration=True
    )
    return group_id


def generate_table(group):
    import ipywidgets as ipw
    from aiida import orm

    # Data to display in the table
    data = {
        "User name": group.user.get_full_name(),
        "User email": group.user.email,
        "Number of nodes": group.count(),
        # "Creation time": group.ctime.strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    node_types = []
    process_types = []
    for node in group.nodes:
        if isinstance(node, orm.ProcessNode):
            process_types.append(node.process_type)
        node_types.append(node.node_type)
    data["Node types"] = ", ".join(set(node_types))
    data["Process types"] = ", ".join(set(process_types))
    # HTML table with inline CSS for styling
    table_style = """
    <style>
        table {
            width: 60%;
            border-collapse: collapse;
        }
        th, td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        tr:nth-child(even) {background-color: #f2f2f2;}
        th {
            background-color: #4CAF50;
            color: white;
        }
    </style>
    """
    
    table_html = f"<h4>Overview of the archive file</h4><div></div><table>{table_style}<tr><th>Key</th><th>Value</th></tr>"
    
    for key, value in data.items():
        table_html += f"<tr><td>{key}</td><td>{value}</td></tr>"
    table_html += "</table>"
    
    table = ipw.HTML(table_html)
    return table

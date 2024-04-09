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

    table_html = f"<h2>Table</h2><div></div><table>{table_style}<tr><th>Key</th><th>Value</th></tr>"

    for key, value in data.items():
        table_html += f"<tr><td>{key}</td><td>{value}</td></tr>"
    table_html += "</table>"

    table = ipw.HTML(table_html)
    return table

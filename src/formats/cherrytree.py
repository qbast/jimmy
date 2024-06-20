"""Convert cherrytree notes to the intermediate format."""

import base64
from pathlib import Path
import logging
import uuid
import xml.etree.ElementTree as ET

import common
import converter
import intermediate_format as imf


LOGGER = logging.getLogger("jimmy")


def convert_table(node):
    table_md = []
    # TODO: a constant row and column count is expected
    # | Syntax | Description |
    # | --- | --- |
    # | Header | Title |
    # | Paragraph | Text |
    for row_index, row in enumerate(node):
        assert row.tag == "row"
        columns = []
        for cell in row:
            assert cell.tag == "cell"
            if cell.text is None:
                cell_text = ""
            else:
                cell_text = cell.text.replace("\n", "<br>")
            columns.append(cell_text)
        table_md.append("| " + " | ".join(columns) + " |")

        if row_index == 0:
            # header row
            separator = ["---"] * len(columns)
            table_md.append("| " + " | ".join(separator) + " |")
    return "\n".join(table_md)


def convert_rich_text(rich_text):
    # TODO: is this fine with mixed text and child tags?
    note_links = []
    if (url := rich_text.attrib.get("link")) is not None:
        if url.startswith("webs "):
            # web links
            url = url.lstrip("webs ")
            if rich_text.text == url:
                md_content = f"<{url}>"
            else:
                md_content = f"[{rich_text.text}]({url})"
        elif url.startswith("node "):
            # internal node links
            url = url.lstrip("node ")
            md_content = f"[{rich_text.text}]({url})"
            note_links.append(imf.NoteLink(md_content, url, rich_text.text))
        else:
            # ?
            md_content = f"[{rich_text.text}]({url})"
    else:
        md_content = "" if rich_text.text is None else rich_text.text
    return md_content, note_links


def convert_png(node, resource_folder):
    # It seems like the <encoded_png> attribute doesn't only cover PNG, but also
    # arbitrary attachments.
    filename = resource_folder / str(uuid.uuid4())
    filename.write_bytes(base64.b64decode(node.text))

    display_name = node.attrib.get("filename", filename.name)
    resource_md = f"![{display_name}]({filename})"
    resource_imf = imf.Resource(filename, resource_md, filename.name)
    return resource_md, resource_imf


def fix_list(md_content):
    md_content = md_content.replace("•", "-")
    return md_content


class Converter(converter.BaseConverter):
    accepted_extensions = [".ctd"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bookmarked_nodes = []

    def convert_to_markdown(self, node, root_notebook):
        # TODO
        # pylint: disable=too-many-locals
        note_name = node.attrib.get("name", "")

        new_root_notebook = None  # only needed if there are sub notes
        resources = []
        note_links = []
        note_body = ""
        for child in node:
            match child.tag:
                case "rich_text":
                    content_md, note_links_joplin = convert_rich_text(child)
                    note_body += content_md
                    note_links.extend(note_links_joplin)
                case "node":
                    # there are sub notes -> create notebook with same name as note
                    if new_root_notebook is None:
                        new_root_notebook = imf.Notebook({"title": note_name})
                        root_notebook.child_notebooks.append(new_root_notebook)
                    LOGGER.debug(
                        f"new notebook: {new_root_notebook.data['title']}, "
                        f"parent: {root_notebook.data['title']}"
                    )
                    self.convert_to_markdown(child, new_root_notebook)
                case "codebox":
                    # TODO: language?
                    note_body += f"```\n{child.text}\n```\n"
                case "encoded_png":
                    # We could handle resources here already,
                    # but we do it later with the common function.
                    resource_md, resource_joplin = convert_png(child, self.root_path)
                    note_body += resource_md
                    resources.append(resource_joplin)
                case "table":
                    note_body += convert_table(child)
                case _:
                    LOGGER.warning(f"ignoring tag {child.tag}")

        note_body = fix_list(note_body)

        note_data = {
            "title": note_name,
            "body": note_body,
            "source_application": self.format,
        }

        # cherrytree bookmark -> joplin tag
        unique_id = node.attrib["unique_id"]
        tags = []
        if unique_id in self.bookmarked_nodes:
            tags.append("cherrytree-bookmarked")

        if (created_time := node.attrib.get("ts_creation")) is not None:
            note_data["user_created_time"] = int(created_time) * 1000
        if (updated_time := node.attrib.get("ts_lastsave")) is not None:
            note_data["user_updated_time"] = int(updated_time) * 1000
        LOGGER.debug(
            f"new note: {note_data['title']}, parent: {root_notebook.data['title']}"
        )
        root_notebook.child_notes.append(
            imf.Note(
                note_data,
                tags=[imf.Tag({"title": tag}) for tag in tags],
                resources=resources,
                note_links=note_links,
                original_id=unique_id,
            )
        )

    def convert(self, file_or_folder: Path):
        self.root_path = common.get_temp_folder()
        root_node = ET.parse(file_or_folder).getroot()

        for child in root_node:
            match child.tag:
                case "bookmarks":
                    # We assume that bookmarks are defined before any nodes.
                    self.bookmarked_nodes = child.attrib.get("list", "").split(",")
                case "node":
                    self.convert_to_markdown(child, self.root_notebook)
                case _:
                    LOGGER.warning(f"ignoring tag {child.tag}")

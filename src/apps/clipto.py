"""Convert clipto notes to the intermediate format."""

from pathlib import Path
import json

from common import iso_to_unix_ms
from intermediate_format import Note, Tag


def convert(file_: Path, root):
    # export only possible in android app:
    # - https://github.com/clipto-pro/Desktop/issues/21#issuecomment-537401330
    # - settings -> time machine -> backup to file

    file_dict = json.loads(Path(file_).read_text(encoding="UTF-8"))
    tags_joplin = []
    # tags are contained in filters
    for filter_ in file_dict.get("filters"):
        tags_joplin.append(Tag({"title": filter_["name"]}, filter_["uid"]))

    joplin_notes = []
    for note_clipto in file_dict.get("notes", []):
        note_joplin = Note(
            {
                "title": note_clipto["title"],
                "body": note_clipto["text"],
                "user_created_time": iso_to_unix_ms(note_clipto["created"]),
                "user_updated_time": iso_to_unix_ms(note_clipto["updated"]),
            },
            tags=note_clipto["tagIds"],
        )
        joplin_notes.append(note_joplin)
        print(note_joplin)

    root.child_notes = joplin_notes
    print(tags_joplin)
    return root, tags_joplin

"""Confirm that manual packet users receive the canonical author skill and references."""
import io
import re
import zipfile

from ctrltea import authoring, sources


def test_packet_ships_canonical_rules_and_every_linked_reference(client, lecture):
    _, document = lecture
    source = sources.register(document["id"], "primary.txt", "نص معتمد".encode(), role="primary")
    sources.extract(source["id"])
    _, raw = authoring.packet(document["id"])
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manual = archive.read("instructions.txt").decode()
        skill = (authoring.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        assert skill.split("\n---\n", 1)[1].lstrip() == manual
        links = set(re.findall(r"\]\((references/[\w-]+\.md)\)", manual))
        assert links == {name for name in archive.namelist() if name.startswith("references/")}
        assert links
        for name in links:
            assert archive.read(name) == (authoring.SKILL_DIR / name).read_bytes()

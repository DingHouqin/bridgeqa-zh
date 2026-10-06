"""Frozen stdlib glyph derivation; not full OpenCC mmseg equivalence.

Input: Unicode text and vendored OpenCC 1.1.9 dictionaries. Output: one
left-to-right longest-phrase/first-candidate pass. S1.1 implementation by the
active agent; source offsets always refer to the unmodified original text.
"""
import hashlib
import json
from pathlib import Path

from .protocol import normalize, stable_hash
from .validation import require

RESOURCES = {
    "TSPhrases.txt": (5181, "504169029c43f7f234b8e2ae470720af3657675c5574ff8aa0feb257e1dc5ce2"),
    "TSCharacters.txt": (34627, "6b5a0a799bea2bb22c001f635eaa3fc2904310f0c08addbff275477a80ecf09a"),
    "LICENSE": (9165, "b534e465949558eec2597b04f5092b5e161236a68dfbfd04d547592ac3964308"),
}
PROFILE = {
    "name": "opencc-derived-longest-first-v1", "upstream_version": "ver.1.1.9",
    "algorithm": "left-to-right; longest phrase first (lexical key tie order); first candidate; otherwise character first candidate; otherwise unchanged; single nonrecursive pass",
    "scope": "glyph conversion, not semantic correction or full OpenCC mmseg equivalence",
    "resource_sha256": {name: sha for name, (_, sha) in RESOURCES.items()},
}


class Converter:
    def __init__(self, root=None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[2]
        directory = self.root / "resources/opencc"
        expected = {"upstream": "BYVoid/OpenCC", "version": "ver.1.1.9", "license": "Apache-2.0", "resources": []}
        raw_resources = {}
        for name, (size, sha) in RESOURCES.items():
            raw = (directory/name).read_bytes()
            require(len(raw) == size and hashlib.sha256(raw).hexdigest() == sha, f"conversion resource hash mismatch: {name}")
            raw_resources[name] = raw
            url = "https://raw.githubusercontent.com/BYVoid/OpenCC/ver.1.1.9/" + ("LICENSE" if name == "LICENSE" else "data/dictionary/"+name)
            expected["resources"].append({"path": name, "url": url, "bytes": size, "sha256": sha})
        require(json.loads((directory/"manifest.json").read_text(encoding="utf-8")) == expected, "conversion resource manifest mismatch")
        require(json.loads((directory/"profile.json").read_text(encoding="utf-8")) == {**PROFILE, "profile_sha256": stable_hash(PROFILE)}, "conversion profile mismatch")
        self.profile = {**PROFILE, "profile_sha256": stable_hash(PROFILE)}
        self.phrases = self._parse(raw_resources["TSPhrases.txt"])
        self.characters = self._parse(raw_resources["TSCharacters.txt"])
        self.by_first = {}
        for key in self.phrases:
            self.by_first.setdefault(key[0], []).append(key)
        for keys in self.by_first.values():
            keys.sort(key=lambda key: (-len(key), key))

    @staticmethod
    def _parse(raw):
        result = {}
        for line in raw.decode("utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            key, values = line.split("\t")
            require(key not in result and bool(values.split()), "duplicate or empty conversion dictionary key")
            result[key] = values.split()[0]
        return result

    def convert(self, text, changes=False):
        index, parts, records, out_index = 0, [], [], 0
        while index < len(text):
            key = next((key for key in self.by_first.get(text[index], []) if text.startswith(key, index)), text[index])
            target = self.phrases.get(key, self.characters.get(key, key))
            parts.append(target)
            if target != key:
                records.append({"original_start": index, "original_end": index+len(key), "derived_start": out_index,
                                "derived_end": out_index+len(target), "original": key, "derived": target})
            index += len(key); out_index += len(target)
        output = "".join(parts)
        return (output, records) if changes else output

    def aliases(self, originals):
        """Deduplicate within entities; reject all normalized cross-entity merges."""
        result, owners, history = {}, {}, []
        for original, aliases in originals.items():
            canonical = self.convert(original)
            require(canonical not in result, "converted canonical collision")
            converted, seen = [], {normalize(canonical)}
            for name in aliases:
                value = self.convert(name)
                if normalize(value) not in seen:
                    converted.append(value); seen.add(normalize(value))
            for value in [canonical, *converted]:
                key = normalize(value)
                require(key not in owners or owners[key] == original, f"converted entity alias collision: {value}")
                owners[key] = original
            result[canonical] = converted
            history.append({"original_canonical": original, "original_aliases": aliases, "canonical": canonical, "aliases": converted})
        return result, history

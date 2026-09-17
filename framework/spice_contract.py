"""Typed SPICE references with explicit physical-component provenance."""

import re


def extract_spice_deck(response):
    """Extract one explicitly fenced deck; never concatenate alternatives."""
    if not isinstance(response, str) or not response.strip():
        raise ValueError('empty SPICE response')
    lines = response.splitlines()
    blocks = []
    current = None
    language = None
    for line in lines:
        fence = re.fullmatch(r'\s*```([^`]*)\s*', line)
        if fence:
            tag = fence.group(1).strip().lower()
            if current is None:
                current, language = [], tag
            else:
                if tag:
                    raise ValueError('nested or malformed code fence')
                blocks.append((language, '\n'.join(current).strip()))
                current = None
        elif current is not None:
            current.append(line)
    if current is not None:
        raise ValueError('unterminated code fence')
    if not blocks:
        return response.strip()
    if len(blocks) != 1 or blocks[0][0] not in {'', 'spice', 'sp', 'cir', 'netlist'}:
        raise ValueError('expected one unambiguous SPICE code block')
    if not blocks[0][1]:
        raise ValueError('empty SPICE code block')
    return blocks[0][1]


def _device_prefix(component, library_id):
    library = str(library_id or "").rsplit(":", 1)[-1]
    sources = [library, str(component.get("search_query", "")),
               str(component.get("name", ""))]
    patterns = (
        ("M", r"\b(?:mosfet|nmos|pmos|2n7000|2n7002|bs170)\b"),
        ("Q", r"\b(?:bjt|npn|pnp|2n3904|2n3906|bc547|bc557)\b"),
        ("X", r"\b(?:op[- ]?amp|lm2904|lm358|lm324)\b"),
        ("D", r"\b(?:diode|zener|led|1n\d+[a-z]*)\b"),
        ("R", r"\b(?:resistor|potentiometer)\b|^R$"),
        ("C", r"\b(?:capacitor)\b|^C(?:_Polarized)?$"),
        ("L", r"\b(?:inductor)\b|^L$"),
        ("V", r"\bvoltage source\b"),
        ("I", r"\bcurrent source\b"),
    )
    for source in sources:
        for prefix, pattern in patterns:
            if re.search(pattern, source, re.IGNORECASE):
                return prefix
    return None


def component_bindings(components, retrieved):
    bindings = []
    used = set()
    for component in components:
        uid = component.get("uid")
        if not uid:
            continue
        uid = str(uid)
        entry = retrieved.get(uid) or {}
        library_id = entry.get("lib_id")
        prefix = _device_prefix(component, library_id)
        reference = None
        if prefix:
            if re.fullmatch(prefix + r"[A-Za-z0-9_]+", uid, re.IGNORECASE):
                reference = uid
            else:
                reference = prefix + "_" + re.sub(r"[^A-Za-z0-9_]", "_", uid)
            base = reference
            suffix = 2
            while reference.upper() in used:
                reference = f"{base}_{suffix}"
                suffix += 1
            used.add(reference.upper())
        bindings.append({"physical_uid": uid, "spice_reference": reference,
                         "library_id": library_id, "spice_prefix": prefix})
    return bindings


def clean_preserving_definitions(code, cleaner):
    """Apply top-level cleanup without editing model/subcircuit definitions."""
    lines = code.splitlines(keepends=True)
    output = []
    pending = []
    index = 0

    def flush():
        if pending:
            output.append(cleaner("".join(pending)).rstrip() + "\n")
            pending.clear()

    while index < len(lines):
        line = lines[index]
        if re.match(r"\s*\.subckt\b", line, re.IGNORECASE):
            flush()
            depth = 0
            while index < len(lines):
                line = lines[index]
                if re.match(r"\s*\.subckt\b", line, re.IGNORECASE):
                    depth += 1
                if re.match(r"\s*\.ends\b", line, re.IGNORECASE):
                    depth -= 1
                output.append(line)
                index += 1
                if depth == 0:
                    break
            if depth:
                raise ValueError("unterminated subcircuit definition")
        elif re.match(r"\s*\.model\b", line, re.IGNORECASE):
            flush()
            output.append(line)
            index += 1
            while index < len(lines) and lines[index].lstrip().startswith("+"):
                output.append(lines[index])
                index += 1
        else:
            pending.append(line)
            index += 1
    flush()
    return "".join(output).rstrip()

# Fixed Model Library

The unified benchmark uses the same compact device models for every method.
Generated candidates reference the catalog; the evaluator supplies the model
definitions after archiving the submitted deck. This library is frozen before
the development pilot, with hashes in `synthesis_20.json` and the qualification
reports. No parameter is fitted to a method's result.

| Model | Source | Scope |
| --- | --- | --- |
| LM2904 | Existing project `framework/spice_models/LM2904.lib`, copied byte-for-byte | Op-amp macro-model with finite gain, poles and output limiting; original comments retained |
| 2N2222 | Existing project `framework/core/spice_engine.py`, `TIER2_MODELS` | NPN compact model, copied without parameter changes |
| LED | Same existing project dictionary | Generic LED model, not a specified commercial LED |
| 1N4733A | Same existing project dictionary | Existing nominal 5.1 V Zener compact model |
| EDA_NMOS | Benchmark-authored generic SPICE Level-1 model | VTO=1 V, KP=0.1 A/V^2, LAMBDA=0.01 V^-1; reference geometry W=10 um, L=1 um. Not a manufacturer device model |

The source `spice_engine.py` was read from
`/Users/zoe/Desktop/CodeX/EDA_Document/EDA_Last/framework/core/spice_engine.py`;
its SHA-256 at extraction was
`8cbbda4f80ce4bc5a8278a32aefcda5117176aaf48804ee1f1780588d5f3c22e`.

Model file hashes:

- `LM2904.lib`: `6e69154b2d088afc5471b15fd88dbfb02b2d7097b74ef32aeb6072ea839a46ac`
- `discrete.lib`: `7bcf8059fb10f04a4fce129594975425677c979e4d6237a6a17922a1fbf8f48c`

The original 2N3904 card contains `Ise=6.734` without a scale suffix. Its physical
parameter provenance has not been verified, so it is not in this fixed catalog.
Public PySpice model examples were inspected for comparison but were not copied
into this benchmark or used to replace catalog parameters.

Measurements are nominal-temperature small-signal AC or DC operating points.
They do not establish transient stability, noise, process variation, hardware
performance, or large-signal input/output swing. The qualification checks the
stated operating conditions and required native-device connectivity.

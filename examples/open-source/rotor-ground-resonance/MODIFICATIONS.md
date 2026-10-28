# Output adaptation

`original/` preserves the four upstream input files byte-for-byte at commit
`3b8c753a497be98efe4f49b5d44f5b0608cdd78b` of
[alexal00/MBDynmodels](https://github.com/alexal00/MBDynmodels/tree/3b8c753a497be98efe4f49b5d44f5b0608cdd78b/GR_MBDyn/cassoni_model).
Every original file contains an explicit GPL version 2 redistribution grant.
Keep these notices and the supplied `COPYING` with redistributed copies.

The runnable `GR_rotor.mbd` comments out the original
`output results: netcdf, no text;` directive and adds an adjacent change notice.
This selects MBDyn's ordinary text outputs, including `.mov`, for the Studio
importer and avoids requiring NetCDF in the configured solver build. All three
included files are byte-identical to their originals. No dimensions, materials,
joints, loading, integration settings or 60-second duration were changed.

Adaptation made 2026-10-27 for Kinemeld. `provenance.json` records source URLs,
revision and hashes. Run `python verify.py` from this folder to check source
integrity and execute the model through the existing bounded solver adapter.
The resulting `verification.json` reports actual execution; raw outputs remain
under the ignored `.runs/` folder. Execution success does not establish agreement
with the original publication, flightworthiness or validation against hardware.

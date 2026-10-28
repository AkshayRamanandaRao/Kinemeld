# Original STEP pendulum link

This is an original homogeneous square-section pendulum link created by
`generate.py`, using OpenCascade. The STEP source is provided under this
project's MIT license; it is not an imported vendor or spacecraft component.

- Length: **1.000 m**. Square cross-section: **0.030 × 0.030 m**.
- Volume: **0.0009 m³**. An assumed homogeneous density of **1333.333 kg/m³**
  gives **1.2 kg**, matching `assembly-single`'s solver body.
- Body-frame principal inertia at the centre of mass: **Ixx = Iyy =
  0.10009 kg·m²**, **Izz = 0.00018 kg·m²**. These use the rectangular-prism
  equations `m*(length² + width²)/12` and `m*(width² + width²)/12`.
- The STEP file stores millimetres, with the link already placed in the
  example's initial world configuration: centre of mass `(0.069586550480,
  0, -0.495134034371) m`, rotated **−8 degrees about global Y**. Its body-local
  pin `(0, 0, 0.5) m` lies at world origin `(0, 0, 0)`.
- Geometry is intended to be attached to `upper_link`; a viewer must transform
  it relative to the initial body pose when showing a solver frame. The STEP
  itself does not define MBDyn mass, inertia, constraints or material.

To regenerate, install `cadquery-ocp` in Python and run
`python examples/step-pendulum/generate.py`. The generated STEP header can
contain a new timestamp, so byte hashes need not match. The checked-in file's
SHA-256 is `21d27f30d5cc9459f70d7d3cc66f61a6e7c6b1a7e4f69b4fd72e2837090d96ac`.
Run `python -m unittest discover -s backend -p test_step_pendulum.py -v` to
check the source fixture, real STEP tessellation, and exact CAD mass properties.

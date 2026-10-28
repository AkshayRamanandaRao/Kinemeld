# NASA Mars 2020 wheel visual reference

This is NASA's 3D-printable **five-inch Mars 2020 wheel**, offered only as a
visual reference. It is not a solver body, a complete rover, a tire/contact
model, a certified engineering drawing or a claim of flight hardware dimensions.

- Source: [NASA 3D Resources, pinned revision](https://github.com/nasa/NASA-3D-Resources/blob/11ebb4ee043715aefbba6aeec8a61746fad67fa7/3D%20Printing/Mars%202020%205%20inch%20wheel/Mars%202020%205%20inch%20wheel.stl)
- Git blob: `2cbaa531f3472cb457aa1d67f0e1cb9d0cd40446`
- SHA-256: `6318740c1ce44b5d4deb85866dd2a2cef9195197019553c78f0c439ab737c4ad`
- 45,328 triangular facets. Its longest spans are approximately 5.0000 source
  units; the source identifies the printable item as five inches. The curated
  reference therefore explicitly uses **inches**. STL itself has no units.
- NASA describes its resource collection as free to download and use; see the
  [NASA 3D Resources repository](https://github.com/nasa/NASA-3D-Resources)
  and [NASA media usage guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/).
  NASA names and identifiers have separate rules; this application does not
  imply NASA endorsement.

To keep binary assets out of the source repository, the STL is optional and
ignored by Git. On this workstation it is present at
`examples/reference/nasa-mars-2020-wheel.stl`. For a fresh checkout, download
the pinned raw file below to that exact location and verify its SHA-256 before
opening the example. The app verifies both byte length and SHA-256 on serving it.

```powershell
$url = 'https://raw.githubusercontent.com/nasa/NASA-3D-Resources/11ebb4ee043715aefbba6aeec8a61746fad67fa7/3D%20Printing/Mars%202020%205%20inch%20wheel/Mars%202020%205%20inch%20wheel.stl'
Invoke-WebRequest -Uri $url -OutFile 'examples/reference/nasa-mars-2020-wheel.stl'
Get-FileHash 'examples/reference/nasa-mars-2020-wheel.stl' -Algorithm SHA256
```

# TEMPO v1 data reference

## What the public page contains

The TEMPO study has two deliberately separate data surfaces:

1. a five-sample atlas of scalar values reported by Zhou et al.; and
2. an editable synthetic six-scan-rate teaching fixture used to exercise the analysis API.

The atlas does not include published CV arrays. The synthetic fixture is not a reconstruction,
digitization, prediction, or fit of the Zhou figures.

## Published scalar atlas

Primary source:

- W. Zhou et al., *Fundamental properties of TEMPO-based catholytes for aqueous redox flow
  batteries: effects of substituent groups and electrolytes on electrochemical properties,
  solubilities and battery performance*, RSC Advances 10 (2020) 21839.
- DOI: <https://doi.org/10.1039/D0RA03424J>
- Article: <https://pubs.rsc.org/en/content/articlehtml/2020/ra/d0ra03424j>
- Supporting information:
  <https://www.rsc.org/suppdata/d0/ra/d0ra03424j/d0ra03424j1.pdf>
- Licence: [CC BY-NC 3.0](https://creativecommons.org/licenses/by-nc/3.0/)
- Source table: Table 1

The interface labels every atlas value:

`◆ PUBLISHED REPORTED VALUE`

This means a curated scalar was transcribed from the cited table. It does not mean the project
possesses the authors' raw instrument file or is endorsed by the authors or publisher.

### Frozen values

| Sample | Reported E0 / V vs SHE | Mean D / cm² s⁻¹ | Reported k0 / cm s⁻¹ | Water solubility / M | 0.5 M KCl solubility / M | Theoretical capacity / Ah L⁻¹ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4-hydroxy-TEMPO (4HT) | 0.812 | 3.14 × 10⁻⁶ | 4.45 × 10⁻³ | 2.11 | 1.25 | 33.5 |
| 4-oxo-TEMPO (4OT) | 0.910 | 4.61 × 10⁻⁶ | 1.05 × 10⁻² | 1.22 | 0.79 | 21.2 |
| 4-amino-TEMPO (4AT) | 0.895 | 3.77 × 10⁻⁶ | 4.01 × 10⁻³ | 5.79 | 4.80 | 128.6 |
| 4-cyano-TEMPO (4CyT) | 0.881 | 6.23 × 10⁻⁶ | 4.29 × 10⁻³ | 2.6 × 10⁻² | not reported | not reported |
| 4-carboxy-TEMPO (4CaT) | 0.776 | 2.64 × 10⁻⁶ | 2.25 × 10⁻³ | 2.1 × 10⁻² | not reported | not reported |

`not reported` is stored as JSON `null`. It is never converted to zero and never omitted from the
comparison table.

### Conditions stay attached to methods

The source used different measurement paths. The UI must not attach one condition note to every
column:

- **Electrochemistry base:** 1 mM analyte, 0.5 M KCl, 5 mm glassy-carbon rotating-disk working
  electrode, Pt-foil counter electrode, SCE reference, potentials reported versus SHE, room
  temperature, at least 20 minutes of nitrogen purge followed by a nitrogen blanket.
- **Formal potential/direct comparison:** base condition plus pH 7, 25 °C, and 25 mV s⁻¹. The
  source records pH adjustment for 4AT and 4CaT.
- **Mean diffusion coefficient:** variable-scan-rate CV at 5, 10, 25, 50, 100, and 200 mV s⁻¹ and
  the Randles–Sevcik method. The product does not add an unreported pH to this condition.
- **Reported k0:** RDE measurements and Koutecký–Levich/kinetic analysis. The application displays
  this source value but does not infer k0 from ordinary CV.
- **Solubility:** UV-visible measurement after 48 hours of equilibration at room temperature, with
  the water or 0.5 M KCl medium attached.

Supporting Figure S2 contains six-rate CV plots, but the project does not have author-supplied raw
x-y arrays. v1 therefore links to the SI and does not embed, digitize, trace, reconstruct, or
generate those plots under a published-data label.

## Reference JSON contract

The browser requests:

`GET /tempo/reference-v1.json`

The record uses `schema_version: "tempo-reference-v1"`, provenance
`published_reported_scalar`, exactly five sample IDs (`4ht`, `4ot`, `4at`, `4cyt`, `4cat`), typed
quantities with status `reported` or `not_reported`, condition and method IDs, and a deterministic
local-record checksum.

The checksum verifies the local curated record's byte identity. It is not a publisher raw-data
checksum and does not prove scientific authorship.

The browser checks schema, DOI, licence, sample identities, source table, provenance, exact frozen
values, null handling, and the presence of condition/method metadata before revealing the atlas. A
failure displays `DATASET UNAVAILABLE`; it does not show hard-coded substitute values.

## Synthetic six-rate fixture

The interactive table is permanently labelled:

`◇ SYNTHETIC TEACHING DATA · NOT A LAB MEASUREMENT`

It starts with the contract's six rates: 5, 10, 25, 50, 100, and 200 mV s⁻¹. Its values are editable
manual peak assignments. They do not come from Zhou et al. The adjacent CV loop is an explanatory
sketch and is not submitted as measured data.

For the frozen request schema, the browser supplies deterministic synthetic trace arrays plus the
reviewed peak table. v1 does no automatic peak picking. Every input change invalidates the previous
response and produces a new request ID and input hash.

## Reuse boundary

The page displays attributed factual scalar values and direct source links. It does not mirror or
adapt publisher figures. The source's non-commercial licence term needs review before any broader
commercial reuse or republication. Tang et al. data and figures are outside v1 because the licence
and transformation/reuse decision is not complete.


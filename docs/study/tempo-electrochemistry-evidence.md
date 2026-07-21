# TEMPO electrochemistry evidence and implementation boundary

## Decision

A defensible public-data implementation is possible now, but only if the product keeps three evidence classes visibly separate:

1. **Published scalar values** copied from a cited table under the paper's stated conditions.
2. **Published curves** shown only by linking to the paper/SI, unless reuse permission and the licence permit redistribution. Values digitized from a plot must be labelled as digitized estimates, never raw experimental data.
3. **Transparent simulation or user-upload analysis** for interactive curves and arbitrary conditions. Simulated output must never inherit a "measured" or "published" badge.

The strongest immediately usable comparison set is Zhou et al. (2020): five TEMPO derivatives measured under one shared aqueous KCl protocol. It gives formal potential, diffusion coefficient, heterogeneous electron-transfer rate constant, solubility, and theoretical capacity in a table. Its supporting information contains multi-scan-rate CV plots, but not downloadable raw current-potential arrays. The article is licensed **CC BY-NC 3.0**, so a public portfolio or recruiting site should not redistribute or adapt its figures/data unless the intended use is clearly non-commercial or permission is obtained. Linking to the article and presenting attributed factual scalar values is lower risk than republishing digitized curves.

Therefore the recommended first release is:

- a five-sample **published property table**;
- a source/conditions panel and links to the article and SI;
- a clearly synthetic CV teaching view, or a user-upload CV calculator;
- no claim that synthetic curves reproduce the authors' measurements;
- no conductivity or solution-resistance value unless independently supplied or measured.

## Primary reference dataset: five TEMPO derivatives

**Primary source:** W. Zhou et al., *Fundamental properties of TEMPO-based catholytes for aqueous redox flow batteries: effects of substituent groups and electrolytes on electrochemical properties, solubilities and battery performance*, RSC Advances 10 (2020) 21839. [Article](https://pubs.rsc.org/en/content/articlehtml/2020/ra/d0ra03424j), [DOI](https://doi.org/10.1039/D0RA03424J), [supporting information PDF](https://www.rsc.org/suppdata/d0/ra/d0ra03424j/d0ra03424j1.pdf), [licence (CC BY-NC 3.0)](https://creativecommons.org/licenses/by-nc/3.0/).

The authors studied 4-hydroxy-TEMPO (4HT), 4-oxo-TEMPO (4OT), 4-amino-TEMPO (4AT), 4-cyano-TEMPO (4CyT), and 4-carboxy-TEMPO (4CaT). Their common electrochemical protocol was a conventional three-electrode cell at room temperature using a 5 mm-diameter glassy-carbon rotating-disk working electrode, Pt-foil counter electrode, and saturated calomel reference electrode; potentials were converted and reported versus SHE. The solution contained 1 mM TEMPO derivative and 0.5 M aqueous supporting electrolyte. It was purged with nitrogen for at least 20 minutes, then held under nitrogen during measurement. The direct five-sample CV comparison used 0.5 M KCl, pH 7, 25 °C, and 25 mV s⁻¹; 4AT and 4CaT solutions were adjusted to pH 7 with dilute HCl or KOH.

### Values published in Table 1

These values may be displayed as **reported by Zhou et al. under the stated protocol**. They must not be presented as condition-independent molecular constants.

| Sample | Solubility, pure water (M) | Solubility, 0.5 M KCl (M) | Theoretical capacity from KCl solubility (Ah L⁻¹) | Formal potential, 0.5 M KCl (V vs SHE) | Mean diffusion coefficient, 0.5 M KCl (cm² s⁻¹) | Heterogeneous rate constant, 0.5 M KCl (cm s⁻¹) |
|---|---:|---:|---:|---:|---:|---:|
| 4HT | 2.11 | 1.25 | 33.5 | 0.812 | 3.14 × 10⁻⁶ | 4.45 × 10⁻³ |
| 4OT | 1.22 | 0.79 | 21.2 | 0.910 | 4.61 × 10⁻⁶ | 1.05 × 10⁻² |
| 4AT | 5.79 | 4.80 | 128.6 | 0.895 | 3.77 × 10⁻⁶ | 4.01 × 10⁻³ |
| 4CyT | 2.6 × 10⁻² | not reported | not reported | 0.881 | 6.23 × 10⁻⁶ | 4.29 × 10⁻³ |
| 4CaT | 2.1 × 10⁻² | not reported | not reported | 0.776 | 2.64 × 10⁻⁶ | 2.25 × 10⁻³ |

Important provenance details:

- The paper labels the potential as `E0`; in a product, call it the paper's **reported formal/equilibrium potential**, not a universal standard potential.
- The reported diffusion coefficient is the average of the oxidized- and reduced-state coefficients.
- Diffusion coefficients came from variable-scan-rate CV and the Randles–Sevcik relation.
- Rate constants came from RDE data and Koutecký–Levich/kinetic analysis, not from the ordinary CV curve alone.
- Solubility was measured by UV-visible spectroscopy after 48 h equilibration of excess sample.
- `NA` in the paper must remain "not reported/not available"; it must not be replaced by zero.

### Multi-scan-rate and cycle evidence

Supporting Figure S2 contains CVs for all five derivatives at **5, 10, 25, 50, 100, and 200 mV s⁻¹**, with anodic and cathodic peak-current-density fits versus the square root of scan rate. This is a valuable matched comparison. However, it is a PDF figure, not a raw-data deposit. Supporting Figure S4 shows cycles 2, 10, 30, 50, and 100 at 100 mV s⁻¹ for all five derivatives and a peak-current-retention summary. Again, the plotted arrays are not supplied as CSV.

A project may link users directly to these figures. Digitization is technically possible, but any extracted x-y values would be approximate, adapted data and subject to CC BY-NC restrictions. If permission is obtained and digitization is used, every record needs: source figure/panel, extraction tool/version, axis calibration points, estimated digitization error, operator/date, and an explicit `digitized_from_figure` label.

The paper also demonstrates why conditions cannot be hidden. Changing the 0.5 M supporting electrolyte among LiCl, NaCl, KCl, NaNO₃, and Na₂SO₄ changed peak current, diffusion coefficient, rate constant, and solubility. For example, the reported 4AT solubility ranges from 2.98 M in Na₂SO₄ to 5.23 M in NaCl. A molecule-only lookup is therefore scientifically incomplete.

## Additional public candidate with actual source-data files

Tang et al. (2025), *Adjusting Hirshfeld charge of TEMPO catholytes for stable all-organic aqueous redox flow batteries*, provides a second useful comparison: [article](https://www.nature.com/articles/s41467-024-55244-4), [supplementary PDF](https://static-content.springer.com/esm/art%3A10.1038%2Fs41467-024-55244-4/MediaObjects/41467_2024_55244_MOESM1_ESM.pdf), [source-data XLSX](https://static-content.springer.com/esm/art%3A10.1038%2Fs41467-024-55244-4/MediaObjects/41467_2024_55244_MOESM5_ESM.xlsx), and [supplementary-data ZIP](https://static-content.springer.com/esm/art%3A10.1038%2Fs41467-024-55244-4/MediaObjects/41467_2024_55244_MOESM3_ESM.zip).

It reports TPP-TEMPO at 0.77 V vs SHE, diffusion coefficient 3.39 × 10⁻⁶ cm² s⁻¹, rate constant 5.37 × 10⁻³ cm s⁻¹, and water solubility 2.3 M. Supplementary Figure 7 contains TPP-TEMPO and TMA-TEMPO CVs at 10, 20, 50, 80, and 100 mV s⁻¹ in 1 M NaCl, and the paper says source data are provided. This is scientifically stronger than plot digitization because the x-y arrays can be audited.

However, its licence is **CC BY-NC-ND 4.0**. It allows non-commercial sharing with attribution but prohibits distribution of adapted material. A transformed, normalized, or repackaged public dataset may be an adaptation. The safe implementation is to link to the publisher's source file and, before mirroring or transforming it, obtain permission or a specific licensing interpretation. It should also remain a separate study because its concentration, electrolyte, and protocol differ from Zhou et al.; values must not be mixed into one apparent controlled benchmark.

## What can be inferred from CV—and what cannot

### Defensible with conditions and assumptions

- **Peak positions** (`Epa`, `Epc`) and peak separation (`ΔEp`) can be read from a sufficiently resolved curve.
- **Midpoint/formal-potential estimate**, commonly `(Epa + Epc)/2`, can be reported for a sufficiently reversible, stable couple, with the reference electrode and conversion stated.
- **Peak-current ratio** and how peak positions/current change with scan rate can support a limited assessment of reversibility or coupled chemistry.
- **Diffusion coefficient** can be estimated from a valid multi-scan-rate series using Randles–Sevcik only when electron number, electrode area, concentration, temperature, units, diffusion-control assumptions, and preprocessing are known. A linear peak-current-versus-square-root-scan-rate plot is a diagnostic, not by itself proof that every assumption holds.
- **Electron-transfer kinetics** can be estimated with a named method and its assumptions. Zhou et al.'s reported `k0` values came from RDE/Koutecký–Levich analysis; the application must not pretend they were extracted from a single stationary-electrode CV.

### Not defensible from CV alone

- **Electrolyte conductivity** and **solution resistance (`Ru`)** are not independently identifiable from a CV trace. Ohmic drop can distort a curve, but many other effects can also shift or broaden peaks.
- **True intrinsic reversibility** cannot be certified from one visually symmetric voltammogram. Uncompensated resistance, mass transfer, electrode preparation, adsorption, and chemical follow-up can produce similar signatures.
- **Solubility, permeability/crossover, long-term molecular stability, capacity fade, Coulombic efficiency, energy efficiency, and flow-battery performance** require separate measurements.
- A CV does not establish a degradation mechanism, causal structure-property relationship, or safe operating lifetime.
- A formal potential reported versus SHE, SCE, Ag/AgCl, Fc/Fc⁺, or another scale is not directly comparable until reference identity, filling solution, temperature, and conversion are documented.

## Solution resistance, iR correction, and conductivity

The IUPAC Gold Book defines the conductivity-cell constant as `Kcell = κR`, where `R` is measured cell resistance and `κ` is conductivity ([IUPAC cell constant](https://goldbook.iupac.org/terms/view/C00918); original electrochemical nomenclature source [DOI](https://doi.org/10.1351/pac197437040499)). Therefore:

- conductivity requires an independently calibrated cell constant plus a resistance measurement;
- resistance without cell geometry/calibration is not conductivity;
- a CV waveform alone supplies neither a calibrated cell constant nor an unambiguous resistance;
- a synthetic calculator may accept `Ru` or `κ` as a user input, but must not claim to have measured it.

For every real CV record, preserve whether iR correction was off, applied during acquisition, or applied afterward; the measured `Ru`; compensation percentage/limit; method used to obtain `Ru` (for example current interrupt or high-frequency impedance); and whether the displayed potential is raw or corrected. Comparing `ΔEp` or kinetic estimates across records without these fields can confuse ohmic distortion with molecular kinetics.

If conductivity is part of the demo, the scientifically clean implementation is a separate calculator: user supplies measured `R` and calibrated `Kcell`, and the system computes `κ = Kcell/R` with units and uncertainty. It must not infer conductivity from the CV.

## Minimum metadata contract

No real curve or derived metric should receive a "comparable" badge unless these fields are present:

- exact compound name, identifier/structure, oxidation state, purity/source;
- analyte concentration;
- solvent, supporting electrolyte identity and concentration, pH;
- temperature and atmosphere/purge;
- working-electrode material, geometric area/diameter, preparation and rotation rate if applicable;
- counter electrode;
- reference electrode, filling solution, reported potential scale, and conversion method;
- potential window, start potential, initial direction, vertex potentials;
- scan rate, cycle number, equilibration and preconditioning;
- raw current or current density and the area used for normalization;
- iR-correction status, measured `Ru`, method, and compensation settings;
- replicate count, uncertainty, and whether the trace is raw, background-subtracted, smoothed, baseline-corrected, or digitized;
- paper/data DOI, exact figure/file/sheet, licence, and retrieval date.

Missing metadata should stay visible as missing. The interface should not silently fill it with typical values.

## Recommended product boundary

### Safe and useful now

1. Show the five Zhou samples and their Table 1 values with a persistent "published values—0.5 M KCl, room temperature" label.
2. Let users compare those scalar values and read a plain-language explanation of how each was measured.
3. Link to the article and SI for the real plotted CVs.
4. Provide an explicitly **synthetic teaching mode** that demonstrates how scan rate, diffusion, `Ru`, capacitance, and kinetic parameters alter an idealized curve. Use published scalar values as labelled parameters only when the model's assumptions match; do not call the generated trace experimental.
5. Provide a **user-upload mode** for raw CSVs, validate the metadata above, calculate transparent descriptors, show formulas/assumptions, and export a provenance manifest.

### Do not ship as a scientific claim

- reconstructed "real" curves generated from Table 1 values;
- exact peak currents or shapes inferred from a PDF image without a digitization label and error estimate;
- conductivity inferred from CV;
- cross-paper rankings that ignore electrolyte, pH, temperature, electrode, reference, or iR correction;
- arbitrary molecule prediction presented as experimental TEMPO data;
- claims that a reversible-looking CV proves flow-battery stability or performance.

## Final assessment

The public evidence is sufficient for a credible **TEMPO electrochemistry evidence explorer and upload calculator**, not yet for a fully public raw-CV benchmark covering many TEMPO molecules. Zhou et al. supplies the best controlled five-sample scalar benchmark and figure-level multi-rate evidence, while Tang et al. supplies auditable source arrays for a smaller, differently conditioned set but under a restrictive non-commercial/no-derivatives licence.

The responsible path is to publish the scalar atlas now, keep interactive generated curves unmistakably synthetic, add user-upload analysis, and request reuse permission or locate a permissively licensed raw repository before presenting publisher data as an embedded multi-sample CV dataset.

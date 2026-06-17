# Meridian

A QGIS plugin for converting between **magnetic**, **true**, and **grid** north for any
location and date — fully offline.

![Meridian](icon_64.png)

## Why

As geologists we deal with azimuths a lot — compass readings, drill collar orientations,
structural logging, downhole surveys. The reference for an azimuth is critical: is it
relative to magnetic north, true north, or the grid system you're working in? When starting
a new project, one of the first tasks is to orient yourself and work out the differences
between these references and how to convert between them.

If they were static it would be easy — but the magnetic field changes over time, and there
are models that predict its effect across the globe and across the years. Sometimes you
don't just need today's difference, but what it was *when a hole was drilled*, so you can
verify the correct adjustment was made.

Meridian aims to make this job a little easier.

## Features

- **Magnetic declination** (D) from bundled World Magnetic Model epochs: WMM2010, WMM2015v2,
  WMM2020, and the high-resolution WMMHR2025 (degree-133).
- **Grid convergence** (γ) computed numerically from the layer CRS — works for any
  projected coordinate system.
- **Grid magnetic angle** (GMA = D − γ) — the single correction you apply in the field.
- **Manual point** — type a lat/long or pick a point off the map.
- **Layer mode** — process an entire point or polygon layer; use a per-feature date field
  or a single date for the whole layer.
- **Model modes** — Auto (best epoch per date), All (one column per model), or a specific
  model.
- **Full field components** — optionally output I, H, F, X, Y, Z.
- **PDF/PNG report** — a north-arrow diagram with worked examples and a parameter table for
  your project documentation.
- **Fully offline** — all WMM coefficient files are bundled; no internet connection required.

## Installation

Once approved on the QGIS Plugin Repository: **Plugins → Manage and Install Plugins →**
search for *Meridian*.

To install manually, copy the `meridian/` folder into your QGIS plugins directory:

```
<profile>/python/plugins/meridian
```

then enable it under **Plugins → Manage and Install Plugins → Installed**.

## Usage

1. Open Meridian from the toolbar or **Plugins → Meridian**.
2. **Manual mode:** enter a lat/long (or click the map), pick a date and model, then
   **Compute**. Save the result as PDF or PNG if you want a documentation snapshot.
3. **Layer mode:** choose a point or polygon layer, optionally select a date field, pick a
   model mode, then **Compute**. A copy of the layer is added to the project with the
   correction fields appended.

## Requirements

- QGIS 3.22 or newer (Qt5 and Qt6 supported).

## Disclaimer

Magnetic declination values are derived from global geomagnetic models (WMM / WMMHR) and are
approximations only. Local magnetic anomalies, crustal variations, and model limitations mean
results may differ from observed values. Always cross-check critical figures against a trusted
independent source before use in survey or safety-critical applications.

## Licence

GNU General Public License v2 — see [LICENSE](LICENSE).

## Acknowledgements

World Magnetic Model coefficient files are public domain, produced by NOAA's National
Centers for Environmental Information.

---

If you find it useful, please [buy me a coffee](https://www.buymeacoffee.com/solasdata) ☕

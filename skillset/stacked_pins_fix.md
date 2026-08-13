---
name: abIDE Stacked Pins (Overlapping Labels) Fix
description: How to avoid overlapping, stacked global net labels when designing JSON files for the abIDE KiCad schematic generator.
---

# Handling Stacked Pins in abIDE `design.json`

When defining nets in a `design.json` file for the `abIDE` plugin, **do not list multiple pins for a component if those pins are physically stacked (located at the exact same coordinates) in the KiCad symbol.**

## The Problem
Many official KiCad symbols (like microcontrollers or USB connectors) have multiple identical power or ground pins (e.g., `GND` on pins 3, 5, 21 for ATmega328P, or `GND` on A1, A12, B1, B12 for USB-C). These pins are often stacked exactly on top of each other in the symbol to save space. 

If you list all these pins in a net array in `design.json` (e.g., `"GND": ["U1.3", "U1.5", "U1.21"]`), `abIDE` will obediently create a net label for *each* pin. Because the pins share the exact same coordinates, the generated labels will be stacked tightly on top of each other or form an overlapping ladder, resulting in an illegible and messy schematic.

## The Solution
To fix this, **only specify the single visible pin** in the `design.json` file.
* Remove the other hidden/stacked pins from the net list array.
* Example: Instead of `"GND": ["U1.3", "U1.5", "U1.21"]`, use just `"GND": ["U1.3"]`.

KiCad's internal electrical rules will still automatically connect the hidden/stacked pins to the net as long as the visible pin is labeled, ensuring your PCB layout remains 100% correct without messing up the schematic visual.

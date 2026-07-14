/**
 * ============================================================
 * PROJECTS DATA
 * ============================================================
 * To add a new project, copy one of the objects below and
 * paste it at the top of the array (newest first).
 *
 * To add images from your Google Drive:
 *   1. Download them from Google Drive
 *   2. Rename them clearly (e.g., "motor_generator_1.jpg")
 *   3. Drop them into /assets/projects/
 *   4. Add them to the images array below
 *
 * Leave images: [] to show a clean placeholder card.
 * ============================================================
 */

const projects = [
  {
    id: "00",
    title: "Nexus Dashboard",
    subtitle: "Active Project",
    date: "July 2026 – Present",
    tags: ["JavaScript", "Data Aggregation", "Market Research", "UI/UX"],
    summary: "Public energy intelligence dashboard with source-aware filtering and research context.",
    description: "Built a dependency-free dashboard for reviewing energy market, grid, and technology reporting. The interface loads a validated JSON feed, supports search and category filters, surfaces source and freshness metadata, and keeps the collection pipeline separate from the public GitHub Pages frontend.",
    driveLink: "nexus/index.html",
    images: []
  },
  {
    id: "01",
    title: "Custom PCB Design using KiCad",
    subtitle: "Active Project",
    date: "October 2025 – Present",
    tags: ["KiCad", "PCB Layout", "Schematic Capture", "Prototyping"],
    summary: "Custom double-sided PCB for an LED heart display.",
    description: "Designing a small KiCad board to drive an LED heart gift. The workflow covers schematic capture, custom footprint creation, double-sided routing, DRC cleanup, current limiting, and Gerber preparation for fabrication.",
    driveLink: "https://drive.google.com/drive/folders/1JS055aBeeJqllbS_LMKwVPxlxvqH-W2E?usp=sharing",
    // Add more images from your Google Drive here, e.g.:
    // { url: "assets/projects/pcb_routed.jpg", caption: "Routed board" }
    images: [
      { url: "assets/projects/pcb_heart.png", caption: "KiCad PCB editor, LED heart layout" }
    ]
  },
  {
    id: "02",
    title: "Micro-Scale Brushless Motor Energy Generation System",
    subtitle: "Completed",
    date: "May 2025 – June 2025",
    tags: ["LTspice", "Rectifier", "Buck Converter", "USB-C", "Soldering"],
    summary: "Portable generator prototype with rectifier, storage, and regulated USB-C output.",
    description: "Built a compact generator around a small brushless motor. The power chain uses a full-wave bridge rectifier, a lithium cell for storage, a buck converter for 5 V output, and a USB-C breakout for charging. The design was validated in LTspice before moving to a soldered breadboard prototype and a permanent enclosure.",
    driveLink: "https://drive.google.com/drive/folders/1JS055aBeeJqllbS_LMKwVPxlxvqH-W2E?usp=sharing",
    // Add more images from your Google Drive here, e.g.:
    // { url: "assets/projects/generator_full.jpg", caption: "Full build" }
    images: [
      { url: "assets/projects/motor_stator.png", caption: "Brushless motor stator, copper windings" }
    ]
  },
  {
    id: "03",
    title: "Salvaged Component Integration & Custom CAD Enclosure",
    subtitle: "Completed",
    date: "July 2024",
    tags: ["LCD Controller", "3D Printing", "SketchUp", "Hardware Retrofit"],
    summary: "ThinkPad display and webcam reused in a wall-mounted monitor.",
    description: "Salvaged a ThinkPad display panel and webcam module, then rewired them as standalone peripherals. An aftermarket LCD controller board drives the display over HDMI and USB-C, and the webcam uses a standard USB interface. The enclosure was designed in SketchUp and 3D-printed in PLA with mounting tabs, cable routing, and ventilation.",
    driveLink: "https://drive.google.com/drive/folders/1JS055aBeeJqllbS_LMKwVPxlxvqH-W2E?usp=sharing",
    // Add more images from your Google Drive here, e.g.:
    // { url: "assets/projects/monitor_finished.jpg", caption: "Finished build" }
    images: [
      { url: "assets/projects/thinkpad_teardown.png", caption: "Lenovo ThinkPad Disassembly & Component Salvage" }
    ]
  },
  {
    id: "04",
    title: "Raspberry Pi LED Pattern Controller",
    subtitle: "Completed",
    date: "January 2024",
    tags: ["Python", "GPIO", "PWM", "Raspberry Pi", "Embedded"],
    summary: "Python GPIO controller for LED patterns on a Raspberry Pi.",
    description: "Wrote Python GPIO code for a Raspberry Pi LED array. The program uses a simple state machine to switch between solid, pulse, chase, and strobe patterns, with PWM dimming for brightness control. I tested timing and thermal behavior across the operating states.",
    driveLink: "https://drive.google.com/drive/folders/1JS055aBeeJqllbS_LMKwVPxlxvqH-W2E?usp=sharing",
    images: [
      { url: "assets/RasPi.JPG", caption: "Raspberry Pi GPIO setup" },
      { url: "assets/BreadBoard.jpg", caption: "LED breadboard circuit" }
    ]
  }
];

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
    id: "01",
    title: "Custom PCB Design using KiCad",
    subtitle: "Active Project",
    date: "October 2025 – Present",
    tags: ["KiCad", "PCB Layout", "Schematic Capture", "Prototyping"],
    summary: "Designing a custom double-sided PCB to drive an LED heart layout — a hands-on deep dive into schematic capture, footprint routing, and DRC-clean design.",
    description: "This project involves designing a small form-factor PCB using KiCad to drive an LED heart display as a family Christmas gift. The workflow covers schematic capture, custom component footprint creation, double-sided board routing, and iterative design-rule-check (DRC) cleanup. Power delivery is handled via a micro-USB connector with appropriate current limiting for the LED array. The project reinforces best practices in component selection, silkscreen documentation, and preparing Gerber files for fabrication.",
    driveLink: "https://drive.google.com/drive/folders/1JS055aBeeJqllbS_LMKwVPxlxvqH-W2E?usp=sharing",
    // Add more images from your Google Drive here, e.g.:
    // { url: "assets/projects/pcb_routed.jpg", caption: "Routed board" }
    images: [
      { url: "assets/projects/pcb_heart.png", caption: "KiCad PCB Editor — LED Heart Layout" }
    ]
  },
  {
    id: "02",
    title: "Micro-Scale Brushless Motor Energy Generation System",
    subtitle: "Completed",
    date: "May 2025 – June 2025",
    tags: ["LTspice", "Rectifier", "Buck Converter", "USB-C", "Soldering"],
    summary: "Built a self-contained portable generator for phone charging, featuring multi-stage AC-to-DC rectification, battery storage, and a regulated USB-C output.",
    description: "Designed and built a compact portable generator system around a small brushless motor. The power chain includes a full-wave bridge rectifier for AC-to-DC conversion, a lithium cell for intermediate energy storage, a buck converter for regulated 5V output, and a USB-C breakout board for device charging. The design was validated in LTspice before moving to a soldered breadboard prototype, which was then migrated to a permanent enclosure. Key engineering challenges included managing voltage ripple, ensuring safe charge/discharge cycles, and selecting appropriately rated passive components.",
    driveLink: "https://drive.google.com/drive/folders/1JS055aBeeJqllbS_LMKwVPxlxvqH-W2E?usp=sharing",
    // Add more images from your Google Drive here, e.g.:
    // { url: "assets/projects/generator_full.jpg", caption: "Full build" }
    images: [
      { url: "assets/projects/motor_stator.png", caption: "Brushless Motor Stator — Copper Windings" }
    ]
  },
  {
    id: "03",
    title: "Salvaged Component Integration & Custom CAD Enclosure",
    subtitle: "Completed",
    date: "July 2024",
    tags: ["LCD Controller", "3D Printing", "SketchUp", "Hardware Retrofit"],
    summary: "Repurposed a Lenovo ThinkPad display and webcam module into a fully functional wall-mounted monitor with a custom 3D-printed enclosure.",
    description: "Rather than discarding a broken ThinkPad laptop, the display panel and integrated webcam module were salvaged and retrofitted into standalone peripherals. An aftermarket LCD controller board was sourced and wired to drive the display over HDMI and USB-C. The webcam module was re-cased and adapted with a standard USB interface. A custom enclosure was designed in SketchUp and 3D-printed in PLA, incorporating mounting tabs, cable management channels, and ventilation slots. The final build functions as a wall-mounted secondary monitor with an integrated webcam.",
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
    summary: "Programmed GPIO control on a Raspberry Pi for responsive LED patterns with PWM-based dimming and a state-driven sequence engine.",
    description: "This project involved writing Python GPIO code to control an array of LEDs connected to a Raspberry Pi's GPIO pins. The software implements a state-machine-based pattern engine that transitions between pre-programmed light sequences (solid, pulse, chase, strobe). PWM dimming is handled using RPi.GPIO's software PWM, with configurable duty cycles for brightness control. The system was tested across all operating states to verify timing accuracy and thermal performance. This project introduced practical embedded programming skills including signal timing, hardware abstraction, and interactive GPIO testing.",
    driveLink: "https://drive.google.com/drive/folders/1JS055aBeeJqllbS_LMKwVPxlxvqH-W2E?usp=sharing",
    images: [
      { url: "assets/RasPi.JPG", caption: "Raspberry Pi GPIO Setup" },
      { url: "assets/BreadBoard.jpg", caption: "LED Breadboard Circuit" }
    ]
  }
];

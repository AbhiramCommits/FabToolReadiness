-- fabtoolreadiness seed lookups: sites, parts, certifications
-- Re-runnable: truncates the tables it populates (and dependents) first.

TRUNCATE training_completions, tech_certifications, certifications,
         technicians, stock_movements, inventory, tool_bom, parts, tools, sites
RESTART IDENTITY CASCADE;

-- ---------------------------------------------------------------------------
-- Sites (4)
-- ---------------------------------------------------------------------------

INSERT INTO sites (site_code, site_name, region) VALUES
    ('HSZ', 'Hsinchu Fab', 'Asia'),
    ('ATX', 'Austin Fab',   'Americas'),
    ('DRS', 'Dresden Fab',  'Europe'),
    ('SGP', 'Singapore Fab', 'Asia');

-- ---------------------------------------------------------------------------
-- Parts (~120)
-- ---------------------------------------------------------------------------

INSERT INTO parts (part_number, description, unit_cost, lead_time_days, is_consumable) VALUES
    -- Vacuum
    ('VAC-0001', 'Turbo pump, 2200 L/s, magnetic bearing', 18500.00, 60, FALSE),
    ('VAC-0002', 'Dry vacuum pump, 800 m3/h', 12500.00, 45, FALSE),
    ('VAC-0003', 'Cryogenic pump, 10-inch', 24000.00, 75, FALSE),
    ('VAC-0004', 'Roughing pump, rotary vane, 500 m3/h', 4200.00, 30, FALSE),
    ('VAC-0005', 'Gate valve, DN250, pneumatic', 3600.00, 25, FALSE),
    ('VAC-0006', 'Throttle valve controller', 2800.00, 30, FALSE),
    ('VAC-0007', 'Capacitance manometer, 1 Torr', 950.00, 20, FALSE),
    ('VAC-0008', 'Cold cathode gauge', 780.00, 20, FALSE),
    ('VAC-0009', 'Turbo pump bearing kit', 2400.00, 35, TRUE),
    ('VAC-0010', 'KF flange seal kit (10-pack)', 45.00, 10, TRUE),
    ('VAC-0011', 'Exhaust silencer element', 320.00, 15, TRUE),
    ('VAC-0012', 'Vacuum pump oil, 5L', 180.00, 10, TRUE),
    -- RF power
    ('RF-0001', 'RF generator, 13.56 MHz, 3 kW', 14500.00, 60, FALSE),
    ('RF-0002', 'Automatic match network, 3 kW', 6800.00, 45, FALSE),
    ('RF-0003', 'Coaxial cable assembly, 6 ft', 850.00, 20, FALSE),
    ('RF-0004', 'RF filter assembly', 1200.00, 25, FALSE),
    ('RF-0005', 'RF power sensor', 1900.00, 30, FALSE),
    ('RF-0006', 'Generator fan tray', 450.00, 20, TRUE),
    ('RF-0007', 'Match motor capacitor', 1300.00, 30, FALSE),
    ('RF-0008', 'RF connector, type N (5-pack)', 120.00, 10, TRUE),
    ('RF-0009', 'Bias match network', 5400.00, 45, FALSE),
    ('RF-0010', 'RF tuning controller board', 2600.00, 35, FALSE),
    ('RF-0011', 'Shielded cable gland kit', 90.00, 7, TRUE),
    ('RF-0012', 'Cooling fan, 24V, high CFM', 75.00, 10, TRUE),
    -- Gas delivery
    ('GAS-0001', 'Mass flow controller, 0-500 sccm', 2800.00, 40, FALSE),
    ('GAS-0002', 'Mass flow controller, 0-50 slm', 3400.00, 40, FALSE),
    ('GAS-0003', 'Pneumatic gas valve, normally closed', 480.00, 15, FALSE),
    ('GAS-0004', 'Gas line particle filter', 65.00, 7, TRUE),
    ('GAS-0005', 'Point-of-use gas filter, 0.003 um', 240.00, 10, TRUE),
    ('GAS-0006', 'Gas regulator, dual-stage', 1150.00, 25, FALSE),
    ('GAS-0007', 'Purge valve assembly', 620.00, 15, FALSE),
    ('GAS-0008', 'VCR gasket, nickel (10-pack)', 85.00, 5, TRUE),
    ('GAS-0009', 'Gas stick control module', 3200.00, 45, FALSE),
    ('GAS-0010', 'Moisture sensor', 1650.00, 30, FALSE),
    ('GAS-0011', 'Restrictor orifice set', 140.00, 10, TRUE),
    ('GAS-0012', 'Check valve, 1/4 in', 95.00, 10, TRUE),
    -- Chamber / wafer handling
    ('ESC-0001', 'Electrostatic chuck, 300 mm', 9800.00, 70, FALSE),
    ('ESC-0002', 'Lift pin set, alumina (3-pack)', 380.00, 20, TRUE),
    ('ESC-0003', 'Ceramic focus ring', 2400.00, 45, FALSE),
    ('ESC-0004', 'Edge ring, silicon', 3100.00, 45, FALSE),
    ('ESC-0005', 'Confinement ring set', 1800.00, 35, FALSE),
    ('ESC-0006', 'Robot blade, end effector', 2200.00, 30, FALSE),
    ('ESC-0007', 'Chamber liner kit', 2900.00, 40, FALSE),
    ('ESC-0008', 'Wafer handling arm seal kit', 260.00, 15, TRUE),
    ('ESC-0009', 'Chamber viewport', 950.00, 20, FALSE),
    ('ESC-0010', 'Substrate heater coil', 1750.00, 35, FALSE),
    ('ESC-0011', 'Ceramic wafer guide set', 720.00, 25, TRUE),
    ('ESC-0012', 'Vacuum wafer paddle', 610.00, 20, FALSE),
    -- CMP
    ('CMP-0001', 'Polishing pad, IC1000', 480.00, 12, TRUE),
    ('CMP-0002', 'Pad conditioner disk', 850.00, 15, TRUE),
    ('CMP-0003', 'Slurry filter housing', 640.00, 20, FALSE),
    ('CMP-0004', 'Slurry filter cartridge', 95.00, 7, TRUE),
    ('CMP-0005', 'Retaining ring', 380.00, 15, TRUE),
    ('CMP-0006', 'Carrier membrane', 210.00, 12, TRUE),
    ('CMP-0007', 'Platen coolant seal kit', 180.00, 10, TRUE),
    ('CMP-0008', 'Slurry pump diaphragm', 145.00, 12, TRUE),
    ('CMP-0009', 'Polishing head assembly', 4200.00, 50, FALSE),
    ('CMP-0010', 'Brush box roller', 260.00, 12, TRUE),
    ('CMP-0011', 'Slurry flow meter', 1100.00, 25, FALSE),
    ('CMP-0012', 'Dresser arm bearing set', 320.00, 15, TRUE),
    -- Litho
    ('LIT-0001', 'Excimer laser tube, ArF', 125000.00, 90, FALSE),
    ('LIT-0002', 'Illuminator lamp, i-line', 3200.00, 30, TRUE),
    ('LIT-0003', 'Reticle pellicle', 890.00, 10, TRUE),
    ('LIT-0004', 'Developer nozzle', 240.00, 10, TRUE),
    ('LIT-0005', 'Resist dispense pump', 2600.00, 35, FALSE),
    ('LIT-0006', 'Resist point-of-use filter', 75.00, 7, TRUE),
    ('LIT-0007', 'Wafer stage encoder', 3800.00, 45, FALSE),
    ('LIT-0008', 'Lens heater assembly', 1450.00, 30, FALSE),
    ('LIT-0009', 'Top-coat filter, 0.05 um', 130.00, 7, TRUE),
    ('LIT-0010', 'Clean dry air filter element', 60.00, 7, TRUE),
    ('LIT-0011', 'Exposure shutter assembly', 5600.00, 60, FALSE),
    ('LIT-0012', 'Stage air bearing pad', 1900.00, 40, FALSE),
    -- Wet process
    ('WET-0001', 'Spray nozzle, flat fan', 180.00, 10, TRUE),
    ('WET-0002', 'Quartz process tube', 6400.00, 60, FALSE),
    ('WET-0003', 'Quartz wafer boat', 3800.00, 50, FALSE),
    ('WET-0004', 'Chemical recirculation pump', 3200.00, 40, FALSE),
    ('WET-0005', 'O-ring, Kalrez, 300 mm', 260.00, 10, TRUE),
    ('WET-0006', 'O-ring kit, Viton, assorted', 140.00, 7, TRUE),
    ('WET-0007', 'Tank level sensor', 780.00, 20, FALSE),
    ('WET-0008', 'Chemical filter, 10-inch', 320.00, 10, TRUE),
    ('WET-0009', 'Heater blanket, quartz tank', 1150.00, 25, FALSE),
    ('WET-0010', 'Drain valve, PVDF', 420.00, 15, FALSE),
    ('WET-0011', 'Megasonic transducer', 2400.00, 35, FALSE),
    ('WET-0012', 'Quick-connect fitting kit', 90.00, 7, TRUE),
    -- Metrology
    ('MET-0001', 'Tungsten-halogen light source', 1450.00, 30, FALSE),
    ('MET-0002', 'Spectrometer detector', 5800.00, 60, FALSE),
    ('MET-0003', 'Reference wafer set', 2600.00, 25, FALSE),
    ('MET-0004', 'Optics module', 7200.00, 70, FALSE),
    ('MET-0005', 'Stage linear guide', 1850.00, 40, FALSE),
    ('MET-0006', 'Vacuum gauge, Pirani', 380.00, 15, FALSE),
    ('MET-0007', 'Lens cap protector', 45.00, 7, TRUE),
    ('MET-0008', 'Calibration standard kit', 950.00, 15, FALSE),
    ('MET-0009', 'Fiber optic cable assembly', 640.00, 20, FALSE),
    ('MET-0010', 'X-ray tube', 16500.00, 90, FALSE),
    ('MET-0011', 'Detector cooling fan', 85.00, 10, TRUE),
    ('MET-0012', 'Interferometer mirror', 3400.00, 50, FALSE),
    -- AMHS
    ('AMH-0001', 'FOUP, 300 mm', 480.00, 20, FALSE),
    ('AMH-0002', 'FOUP door mechanism', 620.00, 20, FALSE),
    ('AMH-0003', 'OHT belt drive', 240.00, 12, TRUE),
    ('AMH-0004', 'Roller assembly, conveyor', 180.00, 10, TRUE),
    ('AMH-0005', 'AMHS sensor, photoeye', 95.00, 7, TRUE),
    ('AMH-0006', 'Stocker crane cable reel', 1150.00, 30, FALSE),
    ('AMH-0007', 'Load port docking plate', 780.00, 20, FALSE),
    ('AMH-0008', 'FOUP cleaner brush set', 110.00, 7, TRUE),
    ('AMH-0009', 'Gripper finger pad kit', 65.00, 7, TRUE),
    ('AMH-0010', 'Crane servo motor', 2200.00, 35, FALSE),
    ('AMH-0011', 'RFID read head', 420.00, 15, FALSE),
    ('AMH-0012', 'Conveyor idler pulley', 55.00, 7, TRUE),
    -- Facilities
    ('FAC-0001', 'HEPA filter, 24x24', 320.00, 15, TRUE),
    ('FAC-0002', 'ULPA filter, 24x48', 540.00, 15, TRUE),
    ('FAC-0003', 'Chiller compressor', 6800.00, 60, FALSE),
    ('FAC-0004', 'Chiller expansion valve', 640.00, 20, FALSE),
    ('FAC-0005', 'Exhaust blower belt', 85.00, 7, TRUE),
    ('FAC-0006', 'Process cooling water filter', 180.00, 10, TRUE),
    ('FAC-0007', 'Scrubber pH sensor', 720.00, 20, FALSE),
    ('FAC-0008', 'Abatement inlet cone', 1450.00, 35, FALSE),
    ('FAC-0009', 'N2 purge regulator', 480.00, 15, FALSE),
    ('FAC-0010', 'Compressed dry air filter element', 130.00, 7, TRUE),
    ('FAC-0011', 'Chiller coolant pump seal kit', 210.00, 10, TRUE),
    ('FAC-0012', 'Exhaust duct pressure sensor', 640.00, 20, FALSE);

-- ---------------------------------------------------------------------------
-- Certifications (~20), two per tool type
-- ---------------------------------------------------------------------------

INSERT INTO certifications (cert_code, cert_name, tool_type, validity_months) VALUES
    ('ETCH-101', 'Dry Etch Chamber Maintenance',     'ETCH',     24),
    ('ETCH-102', 'Etch Process Safety & Gas Handling', 'ETCH',   36),
    ('LITHO-101', 'Scanner Optical Alignment',        'LITHO',    24),
    ('LITHO-102', 'Photoresist Chemistry Handling',   'LITHO',    24),
    ('CVD-201', 'CVD Chamber Preventive Maintenance', 'CVD',      24),
    ('CVD-202', 'Precursor Gas Systems',              'CVD',      36),
    ('PVD-301', 'PVD Target Change & Bonding',        'PVD',      24),
    ('PVD-302', 'Vacuum Interlock Operations',        'PVD',      24),
    ('CMP-401', 'CMP Pad & Slurry Systems',           'CMP',      12),
    ('CMP-402', 'CMP Endpoint Detection',             'CMP',      24),
    ('DIFF-501', 'Furnace Tube Maintenance',          'DIFF',     24),
    ('DIFF-502', 'High Temp Process Safety',          'DIFF',     36),
    ('IMP-601', 'Ion Implant Source Rebuild',         'IMPLANT',  24),
    ('IMP-602', 'Beam Line Tuning',                   'IMPLANT',  24),
    ('MET-701', 'SEM / Defect Review Operation',      'METRO',    24),
    ('MET-702', 'Optical Thin Film Measurement',      'METRO',    24),
    ('WET-801', 'Wet Bench Chemical Safety',          'WETS',     24),
    ('WET-802', 'Quartz Ware Handling',               'WETS',     24),
    ('AMH-901', 'AMHS Robot & OHT Maintenance',       'AMHS',     12),
    ('AMH-902', 'FOUP Handling & RFID Systems',       'AMHS',     12);

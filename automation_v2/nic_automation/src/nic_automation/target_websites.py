website=[
# "https://etender.up.nic.in",
         "https://wbtenders.gov.in"]

CATEGORY_CONFIG = {
    "EPC": {
        "Distribution": {
            "keywords": [
                "Power",
                "Substation", "PSS", "GIS", "AIS",
                "Power Infrastructure", "Electrical Infrastructure",
                "High Voltage Distribution",
                "Overhead Line", "Stringing", "Conductor Stringing",
                "Underground Cabling", "UG Cable",
                "11 KV", "33 KV Line",
                "RDSS", "Revamped Distribution Sector Scheme",
                "Revamped", "Loss Reduction", "Modernization",
                "Off Grid Distribution Modernization",
                "On Grid Distribution Modernization",
                "Bay Extension", "HT Line Distribution",
                "LT Line Distribution", "Augmentation",
                "Reconductoring", "LV Distribution",
                "Rural Electrification",
                "Covered Conductor", "MVCC",
                "RMU", "SCADA", "Compact Substations",
                "HTLS Conductors", "SITC",
                "Supply, Installation, Testing & Commissioning",
            ]
        },

        "Transmission": {
            "keywords": [
                "EPC / turnkey transmission line",
                "EPC / turnkey substation",
                "132 kV / 220 kV transmission line EPC",
                "132/33 kV substation turnkey",
                "132 kV / 220 kV AIS / GIS substation",
                "220/132 kV substation EPC",
                "Design, supply, erection and commissioning of 132 kV transmission line",
                "Design, supply, erection and commissioning of 220 kV transmission line",
                "132 kV GIS substation EPC",
                "220 kV AIS substation turnkey",
                "Augmentation of 132 kV / 220 kV substation",
                "66 kV", "132 kV", "220 kV", "400 kV",
                "HTLS Transmission Line (66 kV to 400 kV)",
                "Reconductoring / Re-Strengthening / Revival of Transmission Line",
                "SITC of Transmission Line Towers / Monopoles",
            ]
        },

        "Solar": {
            "keywords": [
                "EPC Solar Power",
                "Turnkey Solar Projects",
                "Grid Connected Solar",
                "Ground Mounted Solar",
                "Rooftop Solar",
                "Utility Scale Solar",
                "Solar Energy",
                "Design-supply-install solar",
                "Solar PV",
                "Solar Power System",
                "Solar Energy Infrastructure",
                "PV Module EPC",
                "Solar Inverter",
                "Floating Solar",
                "Renewable energy solar",
                "Off-grid solar project",
                "Hybrid solar project",
                "Distributed solar power",
                "Solar microgrid / minigrid",
                "Residential / commercial solar project",
                "Solar Water Pumping System",
                "Battery Energy Storage System (BESS)",
                "Solar Module",
            ]
        },

        "Water": {
            "keywords": [
                "EPC water supply",
                "Turnkey Water Supply",
                "Water Distribution System / Network",
                "Drinking Water",
                "Water Pipeline",
                "Rural / Urban Piped Water Supply",
                "Supply Infrastructure",
                "Integrated water supply",
                "Water Treatment Plant (WTP)",
                "Sewage Treatment Plant (STP)",
                "Water Supply Network",
                "Intake Well",
                "Overhead Reservoir (OHR)",
                "Underground Reservoir (UGR)",
                "Distribution Network Water Supply",
                "Clear Water Reservoir (CWR)",
                "Pipeline Laying",
                "DI Pipeline",
                "Augmentation of Water Supply",
                "Underground Pipeline Irrigation System",
                "Minor Canal",
                "Construction of Distribution System",
                "Rising Main",
                "DI / MS / HDPE Pipeline",
                "Elevated Service Reservoir (ESR)",
                "Pump House",
                "Gravity Pipe Line System",
                "Command Area Development",
                "Raw Water / Clear Water",
                "Retrofitting of Pipes Water Supply",
                "Survey, Investigation, Design & Construction of Piped Water Supply",
                "RWSS", "PH (Public Health)", "WATCO",
                "Irrigation", "Jal Jeevan Mission (JJM)", "AMRUT 2.0",
            ]
        },

        "Railway": {
            "keywords": [
                "EPC Railway Electrification",
                "Turnkey Railway Electrification",
                "Railway Electrification (RE) Work",
                "Overhead Equipment / OHE",
                "25 kV OHE / 25 kV AC Traction",
                "Overhead Electrification / OHE System",
                "Traction Substation / TSS / Traction Power Supply",
                "Feeding Post / Sectioning Post / Sub-sectioning Post",
                "Traction SCADA / SCADA System",
                "Railway Track / Track Doubling / Gauge Conversion",
                "New Railway Line / Railway Line Construction",
                "Railway Bridge / ROB / RUB / Flyover",
                "Railway Siding / Private Siding / Industrial Siding",
                "Metro Rail / Metro / MRTS / RRTS",
                "Signalling and Telecommunication (S&T)",
                "Railway Station / Coaching Depot / Railway Building",
                "Design, Supply, Erection, Testing and Commissioning of Railway Electrification",
                "OPGW (Optical Ground Wire) on Railway",
                "Railway Electrification of Section",
                "Electric Loco / Traction Distribution",
                "Railway EPC / Turnkey Railway Project",
            ]
        },
    },

    "Manufacturing": {
        "Cables": {
            "keywords": [
                "Cable",
                # "LT Power Cables (Armoured or Unarmoured)",
                # "MV Power Cables (Medium Voltage)",
                "Control Cables",
                # "Signalling Cables",
                # "Aerial Bunched (AB) Cables",
                # "PVC Power Cables",
                # "XLPE Power Cables",
            ]
        },

        "Conductors": {
            "keywords": [
                "Conductor",
                "ACSR Conductors",
                # "AAC Conductors",
                # "AAAC Conductors",
                # "AL-59 Conductors",
                # "AL-7 Conductors",
                # "ASTER Conductors",
                # "HTLS (AECC/TS) Conductors",
                # "Medium Voltage Covered Conductors (MVCC)",
            ]
        },
    },
}

# Placeholder: replace with the real list. A tender is skipped if its Work Description contains any of these.
EXCLUSION_KEYWORDS = []

# Tender ID
# Work Description
# EMD Amount 
# EMD Fee Type
# EMD Payable To

# EMD Exemption Allowed	
# EMD Percentage	NA
# EMD Payable At

# Bid Submission End Date
# Tender Value in ₹
# Tenders Documents
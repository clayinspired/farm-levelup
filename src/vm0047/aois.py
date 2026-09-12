"""Sample areas of interest. Replace with real project polygons via --geojson."""

# bbox = (west, south, east, north) in EPSG:4326
SAMPLE_AOIS = {
    # --- Southeast Asia ---
    "id-east-kalimantan": dict(
        bbox=(116.45, 0.45, 116.55, 0.55),
        country="Indonesia",
        note="Imperata grassland / degraded post-logging mosaic, Kutai Kartanegara.",
        dry_season=(6, 9),
    ),
    "kh-mondulkiri": dict(
        bbox=(107.05, 12.30, 107.15, 12.40),
        country="Cambodia",
        note="Deciduous dipterocarp / cleared agricultural frontier.",
        dry_season=(12, 3),
    ),
    "vn-central-highlands": dict(
        bbox=(108.20, 12.60, 108.30, 12.70),
        country="Vietnam",
        note="Degraded hillslope, coffee/cassava margins.",
        dry_season=(1, 4),
    ),
    # --- Africa ---
    "ke-western": dict(
        bbox=(34.75, 0.25, 34.85, 0.35),
        country="Kenya",
        note="Smallholder mosaic near Kakamega, candidate agroforestry.",
        dry_season=(1, 3),
    ),
    "gh-northern": dict(
        bbox=(-1.05, 9.35, -0.95, 9.45),
        country="Ghana",
        note="Guinea savanna, fire-maintained, shea parkland.",
        dry_season=(11, 2),
    ),
    "tz-tabora": dict(
        bbox=(32.75, -5.10, 32.85, -5.00),
        country="Tanzania",
        note="Miombo woodland degraded by charcoal production.",
        dry_season=(6, 9),
    ),
    "mz-zambezia": dict(
        bbox=(36.85, -16.40, 36.95, -16.30),
        country="Mozambique",
        note="Miombo / shifting cultivation mosaic.",
        dry_season=(6, 9),
    ),
    # --- Southeast Asia: the drier, low-cloud, low-tree-cover end of the region.
    # Borneo-style humid sites are cloud-limited; these are where optical ARR
    # screening actually works in SEA.
    "id-sumba": dict(
        bbox=(119.95, -9.75, 120.05, -9.65),
        country="Indonesia",
        note="Sumba savanna grassland, East Nusa Tenggara.",
        dry_season=(7, 9),
    ),
    "mm-magway": dict(
        bbox=(94.80, 20.00, 94.90, 20.10),
        country="Myanmar",
        note="Central dry zone, degraded scrub near Magway.",
        dry_season=(11, 2),
    ),
    "th-isaan": dict(
        bbox=(103.35, 15.45, 103.45, 15.55),
        country="Thailand",
        note="Northeastern sandy cropland, Roi Et / Surin.",
        dry_season=(12, 3),
    ),
    "ph-mindanao": dict(
        bbox=(124.80, 7.55, 124.90, 7.65),
        country="Philippines",
        note="Imperata grassland, Bukidnon uplands.",
        dry_season=(2, 4),
    ),
    "id-timor": dict(
        bbox=(124.20, -9.60, 124.30, -9.50),
        country="Indonesia",
        note="Timor dry savanna, eucalypt parkland.",
        dry_season=(7, 9),
    ),
    # --- Africa: Sahel / ASAL / miombo restoration belts ---
    "ne-zinder": dict(
        bbox=(8.95, 13.75, 9.05, 13.85),
        country="Niger",
        note="Farmer-managed natural regeneration belt, Zinder.",
        dry_season=(11, 2),
    ),
    "ke-makueni": dict(
        bbox=(37.57, -1.85, 37.67, -1.75),
        country="Kenya",
        note="Semi-arid ASAL dryland, Makueni.",
        dry_season=(1, 3),
    ),
    "et-tigray": dict(
        bbox=(39.25, 13.55, 39.35, 13.65),
        country="Ethiopia",
        note="Degraded highland slope under area exclosure, Tigray.",
        dry_season=(11, 2),
    ),
    "tz-shinyanga": dict(
        bbox=(33.37, -3.71, 33.47, -3.61),
        country="Tanzania",
        note="Ngitili enclosure restoration, Shinyanga.",
        dry_season=(6, 9),
    ),
    "bf-centre": dict(
        bbox=(-1.55, 12.30, -1.45, 12.40),
        country="Burkina Faso",
        note="Degraded lateritic plateau, zai restoration zone.",
        dry_season=(11, 2),
    ),
    "sn-kaffrine": dict(
        bbox=(-15.60, 14.05, -15.50, 14.15),
        country="Senegal",
        note="Groundnut basin agroforestry parkland.",
        dry_season=(11, 2),
    ),
    "za-limpopo": dict(
        bbox=(29.40, -23.60, 29.50, -23.50),
        country="South Africa",
        note="Degraded bushveld rangeland, Limpopo.",
        dry_season=(5, 8),
    ),
    "vn-ninh-thuan": dict(
        bbox=(108.85, 11.60, 108.95, 11.70),
        country="Vietnam",
        note="Semi-arid thorn scrub, Ninh Thuan.",
        dry_season=(1, 4),
    ),
    "la-savannakhet": dict(
        bbox=(105.15, 16.45, 105.25, 16.55),
        country="Laos",
        note="Dry dipterocarp margin / paddy mosaic, Savannakhet.",
        dry_season=(12, 3),
    ),
}

/**
 * VM0047 annual stocking-index + eligibility stack — Earth Engine.
 *
 * Use this instead of the STAC pipeline when screening many sites or whole
 * jurisdictions across Southeast Asia / Africa: EE does the compositing
 * server-side, and it is the only easy route to NICFI (4.77 m) and JRC TMF.
 *
 * Paste into https://code.earthengine.google.com/
 * Requires a registered Cloud project. A carbon project is commercial use —
 * check your EE licensing before relying on this in production.
 */

// ---- configure -------------------------------------------------------------
var AOI = ee.Geometry.Rectangle([34.75, 0.25, 34.85, 0.35]);  // Kenya sample
var T0 = 2026;
var N_YEARS = 10;
var SEASON = [12, 2];            // fixed target window (VM0047 s10.5 seasonality)
var CANOPY_THRESHOLD = 30;       // HOST-COUNTRY forest definition crown cover %
var PLOT_SCALE = 30;             // s10.5: plots 0.09 ha .. 10 ha

var years = ee.List.sequence(T0 - N_YEARS, T0);

// ---- Landsat C2 L2 harmonised surface reflectance ---------------------------
function scaleL2(img) {
  var opt = img.select('SR_B.').multiply(2.75e-05).add(-0.2);
  return img.addBands(opt, null, true);
}
function maskL2(img) {
  var qa = img.select('QA_PIXEL');
  var bad = qa.bitwiseAnd(1 << 1).or(qa.bitwiseAnd(1 << 2))
             .or(qa.bitwiseAnd(1 << 3)).or(qa.bitwiseAnd(1 << 4))
             .or(qa.bitwiseAnd(1 << 5));
  return img.updateMask(bad.not());
}
// Band names differ between OLI (L8/9) and ETM+ (L7) — rename to a common set.
var OLI = ['SR_B2','SR_B3','SR_B4','SR_B5','SR_B6','SR_B7'];
var ETM = ['SR_B1','SR_B2','SR_B3','SR_B4','SR_B5','SR_B7'];
var COMMON = ['blue','green','red','nir','swir1','swir2'];

function landsatCol() {
  var l8 = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2').select(OLI, COMMON);
  var l9 = ee.ImageCollection('LANDSAT/LC09/C02/T1_L2').select(OLI, COMMON);
  var l7 = ee.ImageCollection('LANDSAT/LE07/C02/T1_L2').select(ETM, COMMON);
  return l8.merge(l9).merge(l7);
}

// ---- NDFI (Souza et al. 2005) — the SI example VM0047 itself cites ----------
var ENDMEMBERS = [
  [0.0500, 0.0900, 0.0400, 0.6100, 0.3000, 0.1000],  // GV
  [0.1400, 0.1700, 0.2200, 0.3000, 0.5500, 0.3000],  // NPV
  [0.2000, 0.3000, 0.3400, 0.5800, 0.6000, 0.5800],  // soil
  [0.9000, 0.9600, 0.8000, 0.7800, 0.7200, 0.6500]   // cloud
];

function addNDFI(img) {
  var un = img.select(COMMON).unmix(ENDMEMBERS, true, true)
              .rename(['gv','npv','soil','cloud']);
  var shade = ee.Image(1).subtract(un.reduce(ee.Reducer.sum())).rename('shade');
  var gvs = un.select('gv').divide(ee.Image(1).subtract(shade)).rename('gvs');
  var ndfi = gvs.subtract(un.select('npv').add(un.select('soil')))
                .divide(gvs.add(un.select('npv')).add(un.select('soil')))
                .rename('ndfi');
  var ndvi = img.normalizedDifference(['nir','red']).rename('ndvi');
  return img.addBands([ndfi, ndvi, gvs, un.select('soil')]);
}

// ---- season-matched annual composite ---------------------------------------
function seasonFilter(y) {
  y = ee.Number(y);
  var m0 = SEASON[0], m1 = SEASON[1];
  var start = ee.Algorithms.If(ee.Number(m0).lte(m1),
      ee.Date.fromYMD(y, m0, 1), ee.Date.fromYMD(y.subtract(1), m0, 1));
  var end = ee.Date.fromYMD(y, m1, 1).advance(1, 'month');
  return ee.DateRange(ee.Date(start), end);
}

var col = landsatCol();
var annual = ee.ImageCollection(years.map(function (y) {
  y = ee.Number(y);
  var rng = seasonFilter(y);
  var imgs = col.filterBounds(AOI).filterDate(rng.start(), rng.end())
                .map(scaleL2).map(maskL2).map(addNDFI);
  return imgs.select(['ndfi','ndvi','gvs','soil']).median()
             .set('year', y)
             .set('n_scenes', imgs.size())
             .set('system:time_start', ee.Date.fromYMD(y, 1, 1).millis());
}));

// ---- Hansen GFC annual forest reconstruction -------------------------------
var gfc = ee.Image('UMD/hansen/global_forest_change_2025_v1_13');
var tc0 = gfc.select('treecover2000');
var loss = gfc.select('lossyear');
var gain = gfc.select('gain');

var forestByYear = ee.ImageCollection(years.map(function (y) {
  y = ee.Number(y);
  var yi = y.subtract(2000).min(25);
  var lost = loss.gt(0).and(loss.lte(yi));
  var f = tc0.gte(CANOPY_THRESHOLD).and(lost.not())
             .or(gain.and(lost.not()).and(ee.Image(y.gte(2013))));
  return f.rename('forest').set('year', y)
          .set('system:time_start', ee.Date.fromYMD(y, 1, 1).millis());
}));

// ---- SI trend t-10 -> t0: significant negative slope => prior clearing (s8) --
var trend = annual.map(function (img) {
  return ee.Image.constant(ee.Number(img.get('year'))).float().rename('t')
           .addBands(img.select('ndfi')).copyProperties(img);
}).reduce(ee.Reducer.linearFit());   // 'scale' = slope, 'offset' = intercept

var slope = trend.select('scale').rename('si_slope');

// ---- eligibility composite --------------------------------------------------
var maxForest = forestByYear.max().rename('ever_forest_in_window');
var lossInWindow = loss.gt(0).and(loss.gte(T0 - N_YEARS - 2000)).rename('loss_in_window');

var eligibility = slope.addBands(maxForest).addBands(lossInWindow)
    .addBands(annual.filter(ee.Filter.eq('year', T0)).first().select('ndfi').rename('ndfi_t0'));

// ---- inspect / export -------------------------------------------------------
print('annual composites', annual);
print('scenes per year', annual.aggregate_array('n_scenes'));
print('NDFI time series', ui.Chart.image.series(
    annual.select('ndfi'), AOI, ee.Reducer.mean(), PLOT_SCALE, 'system:time_start'));
print('forest fraction', ui.Chart.image.series(
    forestByYear, AOI, ee.Reducer.mean(), PLOT_SCALE, 'system:time_start'));

Map.centerObject(AOI, 12);
Map.addLayer(annual.filter(ee.Filter.eq('year', T0)).first().select('ndfi'),
             {min: -1, max: 1, palette: ['b4462f','ffffff','2f6f4e']}, 'NDFI t0');
Map.addLayer(slope, {min: -0.05, max: 0.05, palette: ['b4462f','ffffff','2f6f4e']},
             'SI slope (red = clearing indicated)');
Map.addLayer(lossInWindow.selfMask(), {palette: ['b4462f']}, 'GFC loss in 10-yr window');

Export.image.toDrive({
  image: eligibility.clip(AOI),
  description: 'vm0047_eligibility_' + T0,
  scale: PLOT_SCALE, region: AOI, maxPixels: 1e10
});

// NICFI (4.77 m) for visual evidence of pre-existing woody biomass.
// Requires separate NICFI sign-up; uncomment once your account is authorised.
// var nicfi = ee.ImageCollection('projects/planet-nicfi/assets/basemaps/africa');
// Map.addLayer(nicfi.filterDate(T0 + '-01-01', T0 + '-06-01').first(),
//              {bands: ['R','G','B'], min: 64, max: 5454, gamma: 1.8}, 'NICFI');

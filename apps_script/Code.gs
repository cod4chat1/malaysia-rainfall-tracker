function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Rainfall Map')
    .addItem('Open interactive state map', 'openRainfallMap')
    .addToUi();
}

function include(filename) {
  return HtmlService.createHtmlOutputFromFile(filename).getContent();
}

function openRainfallMap() {
  const output = HtmlService.createTemplateFromFile('MapDialog')
    .evaluate()
    .setWidth(1120)
    .setHeight(690);
  SpreadsheetApp.getUi().showModalDialog(output, 'Malaysia rainfall map');
}

function getRainfallMapData() {
  const sheet = SpreadsheetApp.getActive().getSheetByName('Map_Data');
  if (!sheet) {
    throw new Error('Map_Data is missing. Refresh the rainfall dashboard first.');
  }
  const values = sheet.getDataRange().getDisplayValues();
  if (values.length < 2) {
    throw new Error('Map_Data has no rainfall observations yet.');
  }
  const headers = values[0];
  return values.slice(1).filter(row => row[0]).map(row => {
    const result = {};
    headers.forEach((header, index) => result[header] = row[index]);
    return result;
  });
}

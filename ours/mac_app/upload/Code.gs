/**
 * CS724 Gesture Collector upload receiver (Google Apps Script web app).
 * Paste into script.google.com while signed in to the PROJECT Gmail. Setup: ours/mac_app/upload/README.md.
 *
 * Script Properties (Project Settings > Script Properties), never in git:
 *   FOLDER_ID  id of the Drive folder "CS724 uploads" (from its URL)
 *   TOKEN      a long random string you make up; the app and test script send it
 *
 * POST JSON {token, session, file, md5, data(base64)}  -> saves <FOLDER>/<session>/<file>
 *   reply {ok:true, md5, bytes, saved_as} | {ok:false, error}
 *   same name + same md5 already there -> ok, not saved again (safe retries)
 *   same name, different md5          -> saved as "name (2).ext"
 * GET ?token=...                        -> {ok:true, folder:<name>}  (connection check only; lists nothing)
 * Nobody can read, list or delete files through this script.
 */
function reply_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

function props_() {
  var p = PropertiesService.getScriptProperties();
  return { folderId: p.getProperty('FOLDER_ID'), token: p.getProperty('TOKEN') };
}

function hex_(bytes) {
  return bytes.map(function (b) { return ('0' + (b & 0xff).toString(16)).slice(-2); }).join('');
}

function safeName_(s) {
  return String(s || '').replace(/[^A-Za-z0-9._ -]/g, '_').slice(0, 120);
}

function doGet(e) {
  var p = props_();
  if (!p.token || !e || !e.parameter || e.parameter.token !== p.token) {
    // diagnosis only: property NAMES and LENGTHS, never values
    var keys = PropertiesService.getScriptProperties().getKeys();
    var given = (e && e.parameter && e.parameter.token) || '';
    return reply_({ ok: false, error: 'token', property_names: keys.map(function (k) { return '[' + k + ']'; }),
                    stored_token_length: p.token ? p.token.length : null, received_length: given.length });
  }
  return reply_({ ok: true, folder: DriveApp.getFolderById(p.folderId).getName() });
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    var p = props_();
    var req = JSON.parse(e.postData.contents);
    if (!p.token || req.token !== p.token) return reply_({ ok: false, error: 'token' });
    var session = safeName_(req.session), file = safeName_(req.file);
    if (!session || !file || !req.data) return reply_({ ok: false, error: 'missing session/file/data' });

    var bytes = Utilities.base64Decode(req.data);
    var md5 = hex_(Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, bytes));
    if (req.md5 && String(req.md5).toLowerCase() !== md5) return reply_({ ok: false, error: 'md5 mismatch', md5: md5 });

    lock.waitLock(30000);
    var root = DriveApp.getFolderById(p.folderId);
    var it = root.getFoldersByName(session);
    var dir = it.hasNext() ? it.next() : root.createFolder(session);

    var name = file, n = 1;
    while (true) {
      var same = dir.getFilesByName(name);
      if (!same.hasNext()) break;
      var f = same.next();
      if (f.getMd5Checksum && f.getMd5Checksum() === md5) {
        return reply_({ ok: true, md5: md5, bytes: bytes.length, saved_as: name, duplicate: true });
      }
      n += 1;
      var dot = file.lastIndexOf('.');
      name = dot > 0 ? file.slice(0, dot) + ' (' + n + ')' + file.slice(dot) : file + ' (' + n + ')';
    }
    dir.createFile(Utilities.newBlob(bytes, 'application/octet-stream', name));
    return reply_({ ok: true, md5: md5, bytes: bytes.length, saved_as: name });
  } catch (err) {
    return reply_({ ok: false, error: String(err) });
  } finally {
    try { lock.releaseLock(); } catch (x) {}
  }
}

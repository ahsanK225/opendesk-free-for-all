const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const mapping=JSON.parse(read('docs/RELEASE_MAPPING.json'));
const manifest=JSON.parse(read('version.json'));
const native=JSON.parse(read('native/version.json'));
assert.deepEqual(manifest,native,'root and native live manifests must describe the same release');
assert.equal(manifest.channel,'stable');
assert.equal(manifest.version,mapping.nextStableRelease.displayVersion);
assert.equal(mapping.nextStableRelease.tag,'v'+manifest.version);
const entries=[...mapping.historicalMapping,{newTag:mapping.nextStableRelease.tag,newDisplayVersion:manifest.version}];
assert.equal(new Set(entries.map(r=>r.newTag)).size,entries.length);
for(const [index,row] of entries.entries()){
  const expected=`${1+Math.floor(index/10)}.${index%10}`;
  assert.equal(row.newDisplayVersion,expected,'history must advance by 0.1 without gaps');
  assert.equal(row.newTag,'v'+expected);
  assert.ok(read('README.md').includes('/releases/tag/'+row.newTag));
  if(row.oldTag){
    const sha=execFileSync('git',['rev-list','-n','1',row.oldTag],{cwd:root,encoding:'utf8'}).trim();
    assert.equal(sha,row.sourceCommit,'original source tags must remain unchanged');
  }
}
for(const crate of ['engine','launcher']){
  const version=read(`native/${crate}/Cargo.toml`).match(/^version = "([^"]+)"/m)[1];
  assert.equal(version,manifest.version+'.0');
}
const prefix=`https://github.com/${mapping.canonicalRepository}/releases/download/v${manifest.version}/`;
assert.equal(manifest.download_url,prefix+`OpenDesk_v${manifest.version}_Portable.exe`);
assert.equal(manifest.installer_url,prefix+`OpenDesk_Setup_v${manifest.version}_Installer.exe`);
for(const key of ['sha256','installer_sha256'])assert.match(manifest[key],/^[a-f0-9]{64}$/);
for(const file of ['README.md','native/README.md','native/RUNTIME_README.md']){
  assert.doesNotMatch(read(file),/native preview|is a \*\*pre-release\*\*|Latest.*v2\.0\.2/i);
}
console.log(`Stable release metadata and ${entries.length} consecutive history versions verified`);

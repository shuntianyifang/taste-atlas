// Official Essentia.js 0.1.3 algorithm; local CPU WASM, no network.
const fs = require('node:fs');
const net = require('node:net');
net.Socket.prototype.connect = () => { throw new Error('Offline melody analysis'); };
const base = './.reference-essentia-js/node_modules/essentia.js';
if (require(base + '/package.json').version !== '0.1.3') throw new Error('Use locked Essentia.js 0.1.3');
const { Essentia, EssentiaWASM } = require(base);
const bytes=fs.readFileSync(process.argv[2]);
if (bytes.length % 4 || bytes.length<44100*2*4 || bytes.length>44100*600*4) throw new Error('Invalid bounded float32 input');
const samples=new Float32Array(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
if (!samples.every(Number.isFinite)) throw new Error('Nonfinite input');
const rms=Math.sqrt(samples.reduce((sum,x)=>sum+x*x,0)/samples.length);
if (rms < 10**(-65/20)) {
    const count=Math.ceil(samples.length/128);
    fs.writeFileSync(process.argv[3],JSON.stringify({pitch:Array(count).fill(0),confidence:Array(count).fill(0),
        elapsed_seconds:0,engine:'Essentia.js 0.1.3 PredominantPitchMelodia',sample_rate:44100,
        hop_size:128,frame_size:2048,equal_loudness:false,guess_unvoiced:false,offline:true,
        abstention:'silence_before_algorithm'}));
    process.exit(0);
}
const engine=new Essentia(EssentiaWASM);
const vector=engine.arrayToVector(samples);
const filtered=engine.EqualLoudness(vector,44100).signal;
const start=performance.now();
const result=engine.PredominantPitchMelodia(filtered);
const pitch=Array.from(engine.vectorToArray(result.pitch));
const confidence=Array.from(engine.vectorToArray(result.pitchConfidence));
if (pitch.length!==confidence.length || !pitch.every(Number.isFinite) || !confidence.every(Number.isFinite)) throw new Error('Invalid melody output');
fs.writeFileSync(process.argv[3],JSON.stringify({pitch,confidence,elapsed_seconds:(performance.now()-start)/1000,
    engine:'Essentia.js 0.1.3 PredominantPitchMelodia',sample_rate:44100,hop_size:128,frame_size:2048,
    equal_loudness:true,guess_unvoiced:false,offline:true}));
result.pitch.delete();result.pitchConfidence.delete();filtered.delete();vector.delete();

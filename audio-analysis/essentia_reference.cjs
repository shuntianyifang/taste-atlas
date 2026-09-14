// Optional numerical reference using the official Essentia WASM distribution.
const fs = require('node:fs');
const net = require('node:net');
net.Socket.prototype.connect = () => { throw new Error('Network forbidden in reference test'); };
const { Essentia, EssentiaWASM } = require('./.reference-essentia-js/node_modules/essentia.js');
const engine = new Essentia(EssentiaWASM);
const frames = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const result = frames.map(frame => {
  const v = engine.arrayToVector(new Float32Array(frame));
  const output = engine.TensorflowInputMusiCNN(v).bands;
  const a = Array.from(engine.vectorToArray(output));
  output.delete(); v.delete();
  return a;
});
fs.writeFileSync(process.argv[3], JSON.stringify(result));

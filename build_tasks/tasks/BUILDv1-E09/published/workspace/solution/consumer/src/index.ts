import { add, name } from './math';

const value = add(20, 22);
if (value !== 42) {
  throw new Error(`unexpected value: ${value}`);
}
console.log(`consumer ok ${name} ${value}`);

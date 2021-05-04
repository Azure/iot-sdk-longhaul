// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for full license information.

function divmod(dividend: number, divisor: number) {
  if (!Number.isInteger(dividend) || !Number.isInteger(divisor)) {
    throw new Error("dividend and divisor must be integers.");
  }
  if (divisor === 0) {
    throw new Error("cannot divide by zero.");
  }
  const mod = dividend % divisor;
  return [(dividend - mod) / divisor, mod];
}

export function msToDurationString(delta: number) {
  // [D:]h:m:s[.UUUUUU]
  delta = Math.trunc(delta);
  let ms, sec, min, hr, day;
  [delta, ms] = divmod(delta, 1000);
  [delta, sec] = divmod(delta, 60);
  [delta, min] = divmod(delta, 60);
  [day, hr] = divmod(delta, 24);
  return (day ? `${day}:` : "") + hr + `:${min}:` + sec + (ms ? "." + `${ms}`.padStart(3, "0") : "");
}

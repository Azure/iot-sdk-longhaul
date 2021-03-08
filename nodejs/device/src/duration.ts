// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for full license information.

export function msToDurationString(delta: number) {
  // [D:]h:m:s[.UUUUUU]
  delta = Math.trunc(delta);
  let [ms, sec, min, hr] = [1000, 60, 60, 24].reduce(
    (accumulator: number[], currentValue) => {
      accumulator.push(delta % currentValue);
      delta = (delta - (delta % currentValue)) / currentValue;
      return accumulator;
    },
    []
  );
  return (
    (delta ? `${delta}:` : "") +
    hr +
    `:${min}:` +
    sec +
    (ms ? "." + `${ms}`.padStart(3, "0") : "")
  );
}

# Turning-dial crowding review

The v0.1.0 quick audit recorded four visible terminal-region tangencies. The green cable met the third finger at 165 degrees and the piston rod at 285 degrees. The red and blue cable ends met their own proximal finger links at 210 degrees.

## Geometry changes

The green terminal moves from x 7.3 to x 2.0 on the same cover. Its cable still ends on the terminal face and passes through the original clamp.

Each finger socket receives one opaque roof with open sides. The roof is a real convex prism in the drawing and the recorder. It extends 4.8 world units over the cable approach and has a 1.3-unit clearance above the port center. The cable retains its original radius, final-approach rule, fitting gap, group, and layer.

Each junction now sits 6.0 units along its 7.4-unit proximal link, rather than at the link midpoint 3.7. Its original dimensions remain unchanged. The socket face, brass port, and cable endpoint all move together. The junction stays supported by its finger link.

The junction move resolves a painter-order cycle introduced by the socket roof. The actual cycle at 135 degrees was palm, cover, red cable, socket roof, junction, root knuckle, and palm. At 300 degrees the blue side had the same cycle. The audit report listed a thumb/piston split because those parts were blocked descendants. Extracting the cycle identified the junction/root-knuckle relation that needed the geometry change.

The final builder diff adds two solids and changes two placements. The audit implementation, tolerances, ownership, layers, exclusions, and existing crowd allowlist remain unchanged.

## Compared alternatives

- Longer brass ferrules alone retained all four original failures.
- Raising the entire cable deck removed the original failures but introduced twelve other route ambiguities.
- Lateral final approaches introduced pinched bends and retained terminal tangencies.
- Endpoints buried inside solid housings failed the terminal-seat audit and were rejected.
- Four-wall hollow guards passed routes but introduced order cycles, swaps, and depth faults. The full audit rejected that prototype.
- Shorter or narrower covers retained the two finger tangencies. Some also lacked the required cable clearance.
- Splitting the roofs or the suggested thumb did not remove the actual cycle and was rejected.
- A distant diagnostic cube inserted before or after the fingers did not alter order results. Constructor order was not the cause.

## Verification

The original builder reproduced the four crowding failures. A non-quick routes audit on the final geometry passes all rest, route, fold, self-overlap, terminal, and crowding checks. A quick order audit passes with zero cycles, forced order picks, or swaps.

Commands run from a temporary anatomy copy with unchanged kit and scripts:

```sh
node examples/turning-dial/build.mjs --audit --only=routes
node examples/turning-dial/build.mjs --audit --quick --only=order
node scripts/turn-check.mjs examples/turning-dial/build.mjs --fidelity
node examples/turning-dial/build.mjs --audit --verbose
```

The subset and quick runs support iteration. The full run is the release gate. Its raw output and exit status are recorded in [the full audit log](turning-dial-full-audit-v0.2.0.txt).

The fidelity check passes with exit status 0, including its planted-error control. The final builder SHA256 is `69afd966fd25aaa3f82355b7254aaef1c17ee0b203e018faa0571c761d6ebaf4`, identical in the repository and temporary anatomy copy.

The full audit passes with exit status 0. Every failure category is zero, including crowding, cycles, forced order picks, swaps, depth, and continuity. The run checks 9,015 order states, 3,254 posed states, and 72 depth-oracle states covering 20,058 overlapping pairs. All 800 continuity halving candidates pass.

Dark and light pages build successfully in the temporary example directory. Browser verification belongs to the release review.

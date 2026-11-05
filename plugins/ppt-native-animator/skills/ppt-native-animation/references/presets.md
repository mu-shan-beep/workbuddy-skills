# Preset behavior

`auto-teaching` is a router, not a ninth style. It selects a profile per slide while keeping the deck's primary effects consistent.

| Preset | Playback | Main behavior |
| --- | --- | --- |
| minimal | mixed | Title and primary content appear automatically in one conservative stage; an explicit answer still waits for a click. |
| microcourse-auto | automatic | Content fades in after the previous stage with short delays. |
| classroom-step | mixed | Main ideas and paragraphs play automatically; explicit answers wait for one click. |
| question-answer | mixed | Question and context play automatically; the answer waits for a click and explanation follows automatically. |
| text-reading | mixed | Reading material and analysis points appear automatically in a paced sequence. |
| process-diagram | mixed | Nodes follow spatial order automatically and use directional wipes. |
| data-analysis | mixed | Data objects and conclusions appear automatically unless an object is explicitly classified as an answer. |
| visual-story | mixed | Main visual and title lead automatically; captions and quotations follow. |

Prefer `question-answer` whenever the slide contains a question plus an answer or explanation. Prefer `minimal` when classification confidence is low.

Durations should normally remain between 250 and 650 milliseconds. Keep a maximum of two primary entrance-effect families per deck.
Ordinary slides group reading-order items into a bounded number of reveal stages. Dense reading slides may use up to nine stages, while simpler presets use fewer. Repeated navigation and brand elements stay static, and small image-label pairs remain together. An explicit answer creates one click gate; it does not turn the surrounding text into click-driven content.

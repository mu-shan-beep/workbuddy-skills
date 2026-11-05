import { FileBlob, PresentationFile } from "@oai/artifact-tool";

if (!process.argv[2]) throw new Error("Pass a PPTX path");
const presentation = await PresentationFile.importPptx(await FileBlob.load(process.argv[2]));
const snapshot = await presentation.inspect({ kind: "slide", maxChars: 2000 });
if (!snapshot.ndjson.includes("slide")) throw new Error("Artifact import produced no slide records");
console.log("Artifact import check passed.");

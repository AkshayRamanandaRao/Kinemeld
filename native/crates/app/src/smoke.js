(() => {
  const deadline = Date.now() + 30000;
  const timer = setInterval(async () => {
    if (!document.querySelector("#solverStatus")?.textContent.includes("MBDyn ready")) {
      if (Date.now() > deadline) { clearInterval(timer); window.mbdynNative.call("smoke-fail", {error:"Backend did not become ready in the embedded viewer."}); }
      return;
    }
    clearInterval(timer);
    try {
      const catalog = await (await fetch("/api/examples")).json();
      const source = await (await fetch("/api/source-examples")).json();
      const model = catalog.examples.find(item => item.id === "pendulum").model;
      model.simulation = {duration:0.1, step:0.005};
      const response = await fetch("/api/run", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({model})});
      const result = await response.json();
      if (!response.ok || !result.ok || result.source !== "MBDyn" || !result.samples?.length) throw new Error(result.error || "MBDyn run failed");
      const hasCanvas = Boolean(document.querySelector("#canvasMount canvas")?.getContext("webgl2"));
      if (!hasCanvas) throw new Error("WebGL2 viewport is unavailable.");
      await window.mbdynNative.call("smoke", {model, result, exampleCount:catalog.examples.length, sourceCount:source.examples.filter(item => item.enabled).length, hasCanvas});
    } catch (error) { window.mbdynNative.call("smoke-fail", {error:String(error)}); }
  }, 250);
})();

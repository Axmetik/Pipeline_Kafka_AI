import { test, expect } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { readFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const python = process.env.E2E_PYTHON || "python3";
const stateFile = resolve(root, "artifacts/mvp/showcase-last.json");
const state = () => existsSync(stateFile) ? JSON.parse(readFileSync(stateFile, "utf8")) : {run_id:""};
const digest = (path: string) => createHash("sha256").update(readFileSync(path)).digest("hex");

test("one command twice: live automatic selection, preserved models and restart", async ({page,request}) => {
  test.skip(process.env.E2E_SHOWCASE !== "1", "Requires prepared Docker stack");
  test.setTimeout(420000);
  const manifest = resolve(root, process.env.MVP_DOCKER_ARTIFACT_MANIFEST || "artifacts/mvp/docker/manifest.json");
  const metadata = JSON.parse(readFileSync(manifest,"utf8"));
  const paths = [manifest, ...Object.values(metadata.artifacts as Record<string,{path:string}>).map(entry => resolve(manifest,"..",entry.path))];
  const hashes = paths.map(digest);
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  let navigations=0;
  page.on("framenavigated",frame=>{if(frame===page.mainFrame())navigations++;});
  const results: object[] = [];
  let priorForecasts: unknown[] = [];
  let priorRun="";
  for(let repetition=0;repetition<2;repetition++) {
    const previous=state().run_id;
    const processHandle=spawn(python,["-m","integration.demo","showcase","--limit","300","--sleep","0.2"],{cwd:root,env:process.env,stdio:["ignore","pipe","pipe"]});
    let log="";
    processHandle.stdout.on("data",data=>{log+=data.toString();});
    processHandle.stderr.on("data",data=>{log+=data.toString();});
    const finished=new Promise<void>((done,fail)=>{
      processHandle.once("error",fail);
      processHandle.once("exit",code=>code===0?done():fail(new Error(log.slice(-5000))));
    });
    void finished.catch(()=>{});
    try {
      await expect.poll(()=>state().run_id,{timeout:60000}).not.toBe(previous);
      const run=state().run_id;
      expect(state().topic).toBe(run);expect(state().group_id).toBe(run);
      await expect(page.getByLabel("Запуск replay")).toHaveValue(run,{timeout:90000});
      const count=async()=>Number(await page.getByTestId("measurement-count").textContent());
      await expect.poll(count,{timeout:90000}).toBeGreaterThan(10);
      const intermediate=await count();expect(intermediate).toBeLessThan(300);
      await expect(page.getByTestId("visible-count")).not.toHaveText("0 точок у вікні");
      await finished;
      await expect.poll(count,{timeout:60000}).toBe(300);
      await expect(page.getByTestId("forecast-count")).toHaveText("600");
      await expect(page.getByTestId("score-count")).toHaveText("900");
      await expect(page.getByTestId("checkpoint-next")).toHaveText("300");
      for(const detector of ["isolation_forest","autoencoder","residual"]) {
        await expect(page.getByTestId("detector-"+detector)).toContainText("experimental");
        await expect(page.getByTestId("detector-"+detector)).toContainText("Готово");
      }
      const forecastPage=await (await request.get("/api/forecasts?run_id="+run+"&limit=1000")).json();
      const forecasts=forecastPage.items;
      expect(forecasts).toHaveLength(600);
      expect(forecasts.filter((f:{purpose:string})=>f.purpose==="primary_forecast")).toHaveLength(300);
      execFileSync(python,["-m","integration.demo","restart"],{cwd:root,env:process.env,stdio:"pipe",timeout:60000});
      const restored=await (await request.get("/api/forecasts?run_id="+run+"&limit=1000")).json();
      expect(restored.items).toEqual(forecasts);
      if(priorRun) {
        const previous=await (await request.get("/api/forecasts?run_id="+priorRun+"&limit=1000")).json();
        expect(previous.items).toEqual(priorForecasts);
      }
      expect(paths.map(digest)).toEqual(hashes);
      expect(log).toContain("Docker build і підготовку моделей пропущено");
      expect(state().phase).toBe("complete");
      expect(state().results.duplicate_deliveries).toBe(0);
      expect(state().results.rejected_messages).toBe(0);
      results.push({run_id:run,intermediate,measurements:300,forecasts:600,scores:900,duplicates:0,rejected:0,checkpoint:300,immutable_forecasts:forecasts.length});
      priorRun=run;priorForecasts=forecasts;
    } finally {
      if(processHandle.exitCode===null){processHandle.kill("SIGINT");await finished.catch(()=>{});}
      if(log)console.log(log);
    }
  }
  expect(navigations).toBe(0);
  expect(errors).toEqual([]);
  const report={runs:results,automatic_selection:true,page_reloads_during_replays:navigations,models_unchanged:true,browser_errors:errors};
  mkdirSync(resolve(root,"artifacts/mvp/showcase-verification"),{recursive:true});
  writeFileSync(resolve(root,"artifacts/mvp/showcase-verification/e2e.json"),JSON.stringify(report,null,2));
  await page.screenshot({path:resolve(root,"artifacts/mvp/showcase-verification/dashboard.png"),fullPage:true});
  console.log("SHOWCASE_VERIFIED "+JSON.stringify(report));
});

"""Format-only PNG copies and explicitly documented crops of CUA JPEG originals.
No resizing, annotations, retouching, values/status edits, or chart reconstruction.
"""
import hashlib,json,math,subprocess
from pathlib import Path
OUT=Path(__file__).resolve().parent

def main():
 regions=json.loads((OUT/'analytics-regions.json').read_text())
 individual=json.loads((OUT/'individual-row-bounds.json').read_text())
 rules=regions['rules']
 jobs=[
  ('01-catalog.png','01-catalog-original.jpg',None),
  ('02-control-forecast.png','control-analytics-full-original.jpg',(1,1,1439,1000)),
  ('03-modified-forecast.png','modified-forecast-full-original.jpg',(1,1,1439,1000)),
  ('04-ml-scores.png','modified-analytics-full-original.jpg',(264,2029,1144,470)),
  ('05-rules-latest.png','modified-analytics-full-original.jpg',(264,math.floor(rules['y'])-20,1144,math.ceil(rules['height'])+40)),
  ('06-hybrid-events.png','hybrid-events-full-original.jpg',(1,1,1439,1000)),
  ('07-return-episodes.png','individual-events-full-original.jpg',(1,1,1439,math.ceil(individual[7]['y']+individual[7]['height']))),
  ('08-control-background.png','control-events-full-original.jpg',(1,1,1439,1000)),
 ]
 manifest=[]
 for output,source,crop in jobs:
  args=['sips','-s','format','png']
  if crop:
   x,y,width,height=crop
   args+=['--cropToHeightWidth',str(height),str(width),'--cropOffset',str(y),str(x)]
  subprocess.run([*args,str(OUT/source),'--out',str(OUT/output)],check=True,stdout=subprocess.DEVNULL)
  assert (OUT/output).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
  manifest.append(dict(png=output,original=source,crop_xywh=crop,operation='format conversion only' if crop is None else 'documented crop + PNG encoding; no resampling',
      original_sha256=hashlib.sha256((OUT/source).read_bytes()).hexdigest(),png_sha256=hashlib.sha256((OUT/output).read_bytes()).hexdigest()))
 (OUT/'screenshots.json').write_text(json.dumps(dict(viewport_css_pixels=[1440,1000],native_capture_format='JPEG',originals_preserved=True,
    no_resizing_annotations_or_data_changes=True,images=manifest),ensure_ascii=False,indent=2)+'\n')
 print('Saved eight PNG copies/crops; unedited native JPEG originals retained.')

if __name__=='__main__':main()

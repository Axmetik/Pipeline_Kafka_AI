"""Ukrainian multipart email; score is never a probability."""
from email.message import EmailMessage
from email.utils import format_datetime
from html import escape

METHODS={'isolation_forest':'Isolation Forest','autoencoder':'Autoencoder','residual':'Forecast Residual Detector'}


def render(row,cfg,delivery_at):
    p=row['payload']
    method=METHODS.get(p['method'],p['method'])
    rows=[('Будівля',p['building_id']),('Джерело',p['source_id']),('Запуск',p['run_id']),
        ('Час вимірювання',p['measurement_timestamp']),
        ('Семантика часу','Час датасету, часовий пояс не визначено' if p['time_basis']=='dataset_naive' else 'Час із підтвердженим UTC offset'),
        ('Час обробки',p['processed_at']),('Час спроби SMTP-доставки (UTC)',delivery_at.isoformat()),
        ('Метод',method),('Статус','Experimental'),('Епізод',p['episode_id'])]
    if p.get('energy_wh') is not None:
        rows.append(('Енергія',f"{p['energy_wh']:g} Wh / {p['interval_seconds']//60} хв"))
    if p['kind']=='combined':
        rows.append(('Спрацювання детекторів',f"{p['trigger_count']}/3: "+', '.join(METHODS.get(x,x) for x in p['triggered_methods'])))
    elif p.get('score') is not None:
        unit='Wh' if p['method']=='residual' else 'шкала моделі'
        rows.extend([('Score',f"{p['score']:g} ({unit})"),('Поріг',f"{p['threshold']:g} ({unit})")])
    warning='Це автоматичне експериментальне попередження про перевищення статистичного порогу. Воно не підтверджує фізичну несправність обладнання. Score не є ймовірністю несправності. Відсутність листів не означає відсутності аномалій.'
    heading='Energy Intelligence — Експериментальне попередження'
    if p.get('delivery_test'): heading+=' [ТЕСТ ДОСТАВКИ]'
    message=EmailMessage()
    message['Subject']=heading;message['From']=cfg.sender;message['To']=row['recipient']
    message['Date']=format_datetime(delivery_at)
    message['Message-ID']=f"<{row['notification_id']}@energy-intelligence.local>"
    message.set_content(heading+'\n\nЗафіксовано початок нового епізоду перевищення порогу.\n\n'+'\n'.join(f'{k}: {v}' for k,v in rows)+'\n\n'+warning)
    cells=''.join('<tr><th style="text-align:left;padding:8px;color:#49635a">'+escape(k)+'</th><td style="padding:8px;overflow-wrap:anywhere">'+escape(str(v))+'</td></tr>' for k,v in rows)
    message.add_alternative('<!doctype html><html lang="uk"><body style="font-family:Arial,sans-serif;background:#f3f7f5;color:#153c2e;padding:24px"><main style="max-width:700px;margin:auto;background:white;padding:28px;border-radius:16px"><p style="color:#227b52">ENERGY INTELLIGENCE · EXPERIMENTAL</p><h1 style="font-size:24px">'+escape(heading)+'</h1><p>Зафіксовано початок нового епізоду перевищення порогу.</p><table style="width:100%;font-size:14px">'+cells+'</table><p style="padding:16px;background:#fff5da;line-height:1.6">'+escape(warning)+'</p></main></body></html>',subtype='html')
    return message

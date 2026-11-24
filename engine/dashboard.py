"""Static HTML dashboard (data/dashboard.html). Free, no services."""
import html
import json
from datetime import datetime
from . import db, planner


def build(c, path):
    rows = sorted(planner.judged(c), key=lambda r: r["published_at"], reverse=True)
    fol = [dict(r) for r in c.execute("select * from followers order by date")]
    arms = planner.arm_stats(rows)
    tests = [dict(r) for r in c.execute("select * from tests order by status, id")]
    queue = [dict(r) for r in c.execute("select id, kind, format, scheduled_at from posts where status='scheduled' order by scheduled_at")]
    crisis = c.execute("select count(*) n from comment_log where kind='crisis'").fetchone()["n"]
    e = html.escape

    def tr(cells):
        return "<tr>" + "".join(f"<td>{x}</td>" for x in cells) + "</tr>"

    body = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>what to text: dashboard</title><style>
body{{font:15px/1.5 -apple-system,Inter,sans-serif;margin:0;background:#fbfaf6;color:#1c1c1e}}
.w{{max-width:1000px;margin:auto;padding:32px 20px}} table{{width:100%;border-collapse:collapse;background:#fff;font-size:13px}}
td,th{{border-bottom:1px solid #eee;padding:6px 8px;text-align:left}} th{{background:#f3f1ea}}
.k{{display:inline-block;background:#fff;border:1px solid #e5e2da;border-radius:10px;padding:12px 16px;margin:4px 8px 4px 0}}
.k b{{font-size:24px;display:block}} h2{{margin-top:32px}}</style></head><body><div class='w'>
<h1>@whattotext: dashboard</h1><p>updated {datetime.now():%b %d, %H:%M}</p>
<div class='k'><b>{fol[-1]['count'] if fol else 0}</b>followers</div>
<div class='k'><b>{len(rows)}</b>published</div>
<div class='k'><b>{len(queue)}</b>scheduled</div>
<div class='k'><b>{crisis}</b>crisis comments answered</div>
<h2>followers</h2><table><tr><th>date</th><th>followers</th></tr>{''.join(tr([f['date'], f['count']]) for f in fol[-21:])}</table>
<h2>arms (format × hook pattern)</h2><table><tr><th>arm</th><th>n judged</th><th>mean score</th><th>median</th></tr>
{''.join(tr([e(' × '.join(k)), v['n'], round(v['mean'],1), round(v['median'],1)]) for k, v in sorted(arms.items(), key=lambda kv: -kv[1]['mean']))}</table>
<h2>tests</h2><table><tr><th>id</th><th>variable</th><th>hypothesis</th><th>status</th><th>result</th></tr>
{''.join(tr([e(t['id']), e(t['variable']), e(t['hypothesis']), t['status'], e(t['result'] or '')]) for t in tests)}</table>
<h2>posts</h2><table><tr><th>published</th><th>kind</th><th>hook</th><th>reach</th><th>shares</th><th>saves</th><th>follows</th><th>skip</th><th>score</th></tr>
{''.join(tr([r['published_at'][:16], r['kind'], f"<a href='{e(r['permalink'] or '#')}'>{e(r['hook'] or r['id'])}</a>", r['reach'], r['shares'], r['saves'], r['follows'], r['skip_rate'], r['score']]) for r in rows[:60])}</table>
<h2>queue</h2><table><tr><th>when</th><th>kind</th><th>format</th><th>id</th></tr>{''.join(tr([q['scheduled_at'][:16], q['kind'], q['format'], q['id']]) for q in queue)}</table>
</div></body></html>"""
    path.write_text(body)
    return path

import asyncio, re
from sqlalchemy import text
from app.shared.infrastructure.config.settings import get_settings
from app.topic.infrastructure.ai.embedding_service import EmbeddingService
from app.worker.db import get_worker_session_factory

BLANKISH = re.compile(r"\n[ \t ]*\n")

def cos(a, b):
    d = sum(x*y for x, y in zip(a, b))
    na = sum(x*x for x in a) ** .5
    nb = sum(x*x for x in b) ** .5
    return d / (na * nb)

async def main():
    s = get_settings()
    emb = EmbeddingService(s.ai)
    f = get_worker_session_factory()
    async with f() as ses:
        topics = (await ses.execute(text("select id,user_id,name,coalesce(description,'') d from topics"))).all()
        rows = (await ses.execute(text(
            "select c.entry_id, e.date_key, c.text from topic_entry_chunks c "
            "join journal_entries e on e.id=c.entry_id order by e.date_key"))).all()

        # 현행 청크 vs 공백줄까지 쪼갠 하위 조각
        subs, owner = [], []
        for r in rows:
            for p in BLANKISH.split(r.text):
                p = p.strip()
                if p:
                    subs.append(p); owner.append((r.entry_id, r.date_key))
        print(f"chunks={len(rows)} -> subparts={len(subs)}")
        vecs = []
        for i in range(0, len(subs), 40):
            vecs.extend(await emb.embed_batch(subs[i:i+40]))

        for t in topics:
            q = t.name + (": " + t.d if t.d else "")
            qv = await emb.embed_text(q)
            best_sub, best_txt = {}, {}
            for (eid, dk), v, txt in zip(owner, vecs, subs):
                c = cos(qv, v)
                if c > best_sub.get((eid, dk), -1):
                    best_sub[(eid, dk)] = c
                    best_txt[(eid, dk)] = txt.replace("\n", " ")[:52]
            cur = {r.entry_id: None for r in rows}
            vs = "[" + ",".join(f"{x:.6f}" for x in qv) + "]"
            crows = (await ses.execute(text(
                "select c.entry_id, min(c.embedding <=> (:v)::vector) d from topic_entry_chunks c "
                "where c.user_id=:u group by c.entry_id"), {"v": vs, "u": t.user_id})).all()
            for r in crows:
                cur[r.entry_id] = 1 - r.d
            print("=" * 78)
            print(f"TOPIC {t.name}  (threshold {s.topic.topic_similarity_threshold})")
            print(f"{'now':>6} {'split':>6}  date        best subpart")
            out = sorted(best_sub.items(), key=lambda kv: -kv[1])
            for (eid, dk), c in out[:12]:
                print(f"{cur[eid]:6.3f} {c:6.3f}  {dk}  {best_txt[(eid, dk)]}")
            print(f"pass now={sum(1 for v in cur.values() if v and v>=0.75)}  "
                  f"pass split={sum(1 for v in best_sub.values() if v>=0.75)}  of {len(cur)}")

asyncio.run(main())

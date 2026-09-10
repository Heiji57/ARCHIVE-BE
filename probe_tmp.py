import asyncio, sys
from sqlalchemy import text
from app.shared.infrastructure.config.settings import get_settings
from app.topic.infrastructure.ai.embedding_service import EmbeddingService
from app.worker.db import get_worker_session_factory

async def main():
    s = get_settings()
    emb = EmbeddingService(s.ai)
    f = get_worker_session_factory()
    async with f() as ses:
        topics = (await ses.execute(text("select id,user_id,name,coalesce(description,'') d from topics"))).all()
        for t in topics:
            q = t.name + (": " + t.d if t.d else "")
            v = await emb.embed_text(q)
            vs = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
            print("=" * 70)
            print(f"TOPIC {t.name!r} query={q!r}  norm={sum(x*x for x in v)**0.5:.4f}")
            rows = (await ses.execute(text("""
                select e.date_key, left(coalesce(e.title,''),28) title, e.retro_type,
                       min(c.embedding <=> (:v)::vector) dmin,
                       max(c.embedding <=> (:v)::vector) dmax,
                       count(*) n
                from topic_entry_chunks c join journal_entries e on e.id=c.entry_id
                where c.user_id=:u group by e.id,e.date_key,e.title,e.retro_type
                order by dmin asc
            """), {"v": vs, "u": t.user_id})).all()
            print(f"{'sim':>6} {'worst':>6} {'n':>2} date       type    title")
            for r in rows:
                mark = "PASS" if (1 - r.dmin) >= s.topic.topic_similarity_threshold else "    "
                print(f"{1-r.dmin:6.3f} {1-r.dmax:6.3f} {r.n:2d} {r.date_key} {r.retro_type:7s} {r.title} {mark}")
            trows = (await ses.execute(text("""
                select left(te.text,40) txt, te.status, te.embedding <=> (:v)::vector d
                from topic_todo_embeddings te where te.user_id=:u order by d asc
            """), {"v": vs, "u": t.user_id})).all()
            print("-- todos --")
            for r in trows:
                mark = "PASS" if (1 - r.d) >= s.topic.topic_similarity_threshold else "    "
                print(f"{1-r.d:6.3f} {r.status:12s} {r.txt} {mark}")

asyncio.run(main())

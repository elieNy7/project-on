import sqlite3

conn = sqlite3.connect(r'F:\Project\Project-On\data\project_on.db')

# Rename sermon title
conn.execute(
    "UPDATE sermon SET title = ? WHERE id = ? AND tradition = ?",
    ("LE PROPHETE DU 20e SIECLE", 3882, "SHP")
)

# Update paragraph refs that contain the old title
cursor = conn.execute(
    "SELECT id, ref FROM sermon_paragraph WHERE sermon_id = ?", (3882,)
)
rows = cursor.fetchall()
for row in rows:
    pid, ref = row[0], row[1]
    if ref and "SIECLE" in ref:
        new_ref = ref.replace("SIECLE", "LE PROPHETE DU 20e SIECLE")
        conn.execute("UPDATE sermon_paragraph SET ref = ? WHERE id = ?", (new_ref, pid))

conn.commit()

# Verify
row = conn.execute("SELECT title FROM sermon WHERE id = ?", (3882,)).fetchone()
print(f"New title: {row[0]}")

refs = conn.execute(
    "SELECT paragraph_no, ref FROM sermon_paragraph WHERE sermon_id = ? LIMIT 5",
    (3882,)
).fetchall()
for r in refs:
    print(f"  para {r[0]}: ref={r[1]}")

conn.close()
print("Done!")

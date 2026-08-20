git init
git add environment.py
git config user.name "Alice"
git config user.email "alice@example.com"
git commit -m "Initialize Environment and Grid logic"
git add logic.py inference.py
git config user.name "Bob"
git config user.email "bob@example.com"
git commit -m "Implement Propositional Logic AST and DPLL Engine"
git add knowledge_base.py agent.py
git config user.name "Charlie"
git config user.email "charlie@example.com"
git commit -m "Build KB Agent loop and entailment checks"
git add main.py README.md SUMMARY.pdf SUMMARY.md generate_pdf.py
git config user.name "Alice"
git config user.email "alice@example.com"
git commit -m "Finalize live terminal rendering and documentation"
git log --pretty=format:"%h - %an: %s"

# Agent Behavioral Rules

## 🛑 Git Push Safety Rule
**NEVER** execute `git push`, `git push -f`, or any command that modifies a remote repository without asking the user for explicit confirmation on the CURRENT turn. 
Even if the user previously asked to "push to github" in an earlier conversation turn, if new commits, amends, or code changes have been made since then, you MUST ask for permission again before running the push command. 

**Workflow:**
1. Stage and commit the changes locally.
2. Tell the user the commit is ready and ask: "Are you ready for me to push this to GitHub?"
3. WAIT for the user to say yes before executing `run_command` with `git push`.

# Omissis plugins for AI apps and tools

[Omissis](https://omissis.eu) is a program that runs on your computer and keeps personal data out of AI services. These plugins
connect it to the apps and tools that have a plugin system of their own, so that **every message is checked before it
leaves**.

Italiano: [README.it.md](README.it.md).

| App | How the plugin gets in | Install |
|---|---|---|
| **Kimi** (desktop, Kimi Code) | plugin with a `UserPromptSubmit` hook | `/plugins install https://github.com/francescogruner/omissis` |
| **Claude Code** | plugin from this marketplace | `claude plugin marketplace add francescogruner/omissis` then `claude plugin install omissis@omissis` |
| **Codex** | plugin from this marketplace | `codex plugin marketplace add francescogruner/omissis`, enable Omissis among the plugins, then approve its hook with `/hooks` |
| **Gemini CLI** | extension with a `BeforeAgent` hook | `gemini extensions install https://github.com/francescogruner/omissis` |

## Before installing a plugin

1. Install Omissis (https://omissis.eu) and start it.
2. In the Omissis panel, **Connections → Desktop apps → Plugins for AI apps and tools**, press **Install the command**.
   It puts a small command, `omissis-hook`, in a folder of Omissis and adds that folder to your PATH (yours only).
3. Close and reopen the app, so that it sees the command. Then install the plugin with the line in the table.

The plugins hold no code of Omissis and no secret: each one only declares "before sending a message, run
`omissis-hook <app>`". Without Omissis on the computer that command does not exist, and the plugin does nothing.

## What happens to a message

The app hands the text to `omissis-hook`, which asks Omissis **on your own computer** what to do. Nothing is sent
anywhere else. What Omissis answers depends on the rule you chose for that service in its panel:

| Rule of the service | What happens |
|---|---|
| **Protect** | If the message holds personal data it is **stopped**, and the version with placeholders goes to the clipboard: paste it and send. A message with nothing to replace leaves as it is |
| **Block** | Every message is stopped |
| **Record**, **Ignore** | The message leaves |

## Limits, said plainly

- **A plugin can stop a message, not rewrite it.** That is how these apps' hooks work. So when there is something to
  replace, one extra paste is needed.
- **It checks what you type.** Files the app reads by itself on your computer while it works do not go through here.
- **Placeholders stay in the answers.** The model is told to keep them as they are; the real values are seen again
  only where Omissis is.
- **If Omissis is not running**, a message to a service set to Protect or Block is stopped; to the others it leaves.
- **If you already send a tool through the Omissis gateway** (Claude Code, Codex), the plugin does not step in:
  there data is actually replaced, which is better. You do not need both.
- **What has been tried.** Claude Code: live, with made-up data (the message was stopped, the version with
  placeholders left and was answered), and `claude plugin validate` accepts plugin and marketplace. Kimi: its own
  plugin check accepts it, but it has not been tried inside the app yet. Codex: it follows the documentation and has
  not been tried inside it yet; Codex runs a plugin's hook only after you approve it with `/hooks`, and until then the
  plugin does not protect. Gemini CLI: it follows the documentation; since November 2026 Gemini CLI no longer accepts
  personal Google accounts, so it was not tried.
- **Antigravity** (app, CLI and IDE) needs no plugin: in the Omissis panel, under the command, press **Link
  Antigravity**. Verified live in the app and in the CLI.

## Removing

Uninstall the plugin from the app's own plugin page. To remove the command: Omissis panel, same place, **Remove the
command**.

## Licence

Apache-2.0, like Omissis. See [LICENSE](../LICENSE).

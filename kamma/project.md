# Project: Epitaka Translator (fork)

## What it is and why
A fork of the upstream Epitaka translator (dhammanana/epitaka_app). It
translates Pāli Theravāda books (Tipiṭaka, commentaries, sub-commentaries)
into modern languages with an LLM, one book at a time. Each language builds
up its own SQLite file that the Epitaka app reads directly.

The fork exists to adapt the tool to my own needs first: new languages,
better references for Indian languages, more API providers and keys. Changes
that are useful to everyone go back upstream as pull requests.

## Who it's for
- Me, running translations into new target languages.
- The upstream maintainer, who receives the general-purpose changes.
- Readers of the Epitaka app, who get the finished translations.

## One-off or ongoing
Ongoing. The first milestone is a Kannada test run. More languages and
changes follow.

## What it will produce
- Changes to the translator code (reference databases, API providers, keys).
- `epitaka_<lang>.db` and `glossary_<lang>.db` files for each target language.
- Pull requests upstream for changes that are not specific to this fork.

## How you'll know it worked
For each new language: one short sample book translates to the end, with no
wrong-script rows saved and no crashes.

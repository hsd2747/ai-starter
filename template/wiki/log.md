# Wiki log

Append-only history of wiki writes. Oldest first: add new entries at the bottom and never edit a past entry.

Entry format:

```
## [YYYY-MM-DD] <op> | <title>
Source: <task, ticket, or request>
Created: [[slug]], ... | Updated: [[slug]], ...
Not stored: <rejected candidate> (<reason>)
```

Operations: `setup`, `add`, `update`, `learn`, `correct`, `lint`, `refresh`, `migrate`.

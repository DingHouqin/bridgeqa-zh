// [Shared review storage](../../specs/08_临时人工审查.md).
import {sqliteTable,text,integer,primaryKey} from 'drizzle-orm/sqlite-core';
export const reviewEntries=sqliteTable('review_entries',{
  round:text('round').notNull(),kind:text('kind').notNull(),id:text('id').notNull(),
  value:text('value').notNull(),revision:integer('revision').notNull(),updatedAt:text('updated_at').notNull(),
},table=>[primaryKey({columns:[table.round,table.kind,table.id]})]);

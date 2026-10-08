CREATE TABLE `review_entries` (
	`round` text NOT NULL,
	`kind` text NOT NULL,
	`id` text NOT NULL,
	`value` text NOT NULL,
	`revision` integer NOT NULL,
	`updated_at` text NOT NULL,
	PRIMARY KEY(`round`, `kind`, `id`)
);

#!/usr/bin/env python3

import sqlite3
import argparse
import sys


def execute_sql(database, sql):
    try:
        conn = sqlite3.connect(database)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(sql)

        # Handle SELECT queries
        if cursor.description:
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            # Calculate column widths
            widths = []
            for col in columns:
                max_width = len(col)
                for row in rows:
                    max_width = max(max_width, len(str(row[col])))
                widths.append(max_width)

            # Print header
            header = " | ".join(col.ljust(widths[i]) for i, col in enumerate(columns))
            separator = "-+-".join("-" * w for w in widths)

            print(header)
            print(separator)

            # Print rows
            for row in rows:
                print(" | ".join(str(row[col]).ljust(widths[i]) for i, col in enumerate(columns)))

            print(f"\nRows returned: {len(rows)}")

        else:
            conn.commit()
            print(f"Query executed successfully.")
            print(f"Rows affected: {cursor.rowcount}")

    except sqlite3.Error as e:
        print(f"SQLite Error: {e}", file=sys.stderr)
        sys.exit(1)

    finally:
        if conn:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description="Execute SQL against a SQLite database.")
    parser.add_argument("database", help="Path to the SQLite database file")
    parser.add_argument("sql", help="SQL statement to execute")

    args = parser.parse_args()

    execute_sql(args.database, args.sql)


if __name__ == "__main__":
    main()
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from dataclasses import dataclass


@dataclass
class MonthInfo:
    """Information about a specific month for reporting"""
    month_name: str
    month_number: int
    year: int
    start_timestamp: float
    end_timestamp: float
    display_name: str


class MonthSelector:
    """Utility class for handling month selection and timestamp calculations"""

    def __init__(self):
        self.month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]

    def get_available_months(self, count: int = 3) -> List[MonthInfo]:
        """
        Get the last N months (excluding current month) for report generation

        Args:
            count: Number of previous months to return (default: 3)

        Returns:
            List of MonthInfo objects for the last N months
        """
        months = []
        today = datetime.now()

        for i in range(1, count + 1):
            # Calculate the target month by going back i months
            target_date = today.replace(day=1) - timedelta(days=1)
            for _ in range(i - 1):
                target_date = target_date.replace(day=1) - timedelta(days=1)

            # Get first and last day of the target month
            first_day = target_date.replace(day=1)
            if target_date.month == 12:
                last_day = target_date.replace(year=target_date.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                last_day = target_date.replace(month=target_date.month + 1, day=1) - timedelta(days=1)

            # Create timestamps (start of day for first day, end of day for last day)
            start_timestamp = first_day.timestamp()
            end_timestamp = (last_day.replace(hour=23, minute=59, second=59)).timestamp()

            month_info = MonthInfo(
                month_name=self.month_names[target_date.month - 1],
                month_number=target_date.month,
                year=target_date.year,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                display_name=f"{self.month_names[target_date.month - 1]} {target_date.year}"
            )
            months.append(month_info)

        return months

    def get_quarterly_date_range(self) -> Tuple[float, float]:
        """
        Get start and end timestamps for a rolling 3-month window ending at
        the last day of the previous month.
        """
        import calendar
        today = datetime.now()
        end_month_date = today.replace(day=1) - timedelta(days=1)
        end_year  = end_month_date.year
        end_month = end_month_date.month
        last_day  = calendar.monthrange(end_year, end_month)[1]
        end_dt    = datetime(end_year, end_month, last_day, 23, 59, 59)
        start_month = end_month - 2
        start_year  = end_year
        if start_month <= 0:
            start_month += 12
            start_year  -= 1
        start_dt = datetime(start_year, start_month, 1, 0, 0, 0)
        return start_dt.timestamp(), end_dt.timestamp()

    def get_month_by_name(self, month_name: str) -> MonthInfo:
        """
        Get month information by month_year format (e.g., "november_2024")

        Args:
            month_name: Month in 'month_year' format (e.g., "november_2024", "january_2025")
                       Must be lowercase month name, underscore, then 4-digit year

        Returns:
            MonthInfo object for the specified month

        Raises:
            ValueError: If month_name format is invalid or month doesn't exist
        """
        # Validate format: must contain underscore
        if '_' not in month_name:
            raise ValueError(
                f"Invalid month format: '{month_name}'. "
                f"Expected format: 'monthlowercase_year' (e.g., 'november_2024')"
            )

        # Parse month_year format
        parts = month_name.split('_')
        if len(parts) != 2:
            raise ValueError(
                f"Invalid month format: '{month_name}'. "
                f"Expected format: 'monthlowercase_year' (e.g., 'november_2024')"
            )

        month_part = parts[0].lower()
        year_part = parts[1]

        # Validate year is numeric and 4 digits
        if not year_part.isdigit() or len(year_part) != 4:
            raise ValueError(f"Invalid year: '{year_part}'. Year must be a 4-digit number.")

        year = int(year_part)

        # Find month number from month name
        try:
            month_number = next(
                i + 1 for i, name in enumerate(self.month_names)
                if name.lower() == month_part
            )
            month_name_capitalized = self.month_names[month_number - 1]
        except StopIteration:
            raise ValueError(
                f"Invalid month name: '{month_part}'. "
                f"Valid months: {', '.join([m.lower() for m in self.month_names])}"
            )

        # Calculate timestamps for the specified month and year
        first_day = datetime(year, month_number, 1)

        # Get last day of month
        if month_number == 12:
            last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(year, month_number + 1, 1) - timedelta(days=1)

        # Create timestamps (start of day for first day, end of day for last day)
        start_timestamp = first_day.timestamp()
        end_timestamp = (last_day.replace(hour=23, minute=59, second=59)).timestamp()

        return MonthInfo(
            month_name=month_name_capitalized,
            month_number=month_number,
            year=year,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            display_name=f"{month_name_capitalized} {year}"
        )

    def get_month_timestamps(self, month_name: str = None) -> Tuple[float, float]:
        """
        Get start and end timestamps for a specific month or default to previous month

        Args:
            month_name: Name of the month (optional, defaults to previous month)

        Returns:
            Tuple of (start_timestamp, end_timestamp)
        """
        if month_name and month_name.strip().lower() == "last_3_months":
            return self.get_quarterly_date_range()
        if month_name:
            month_info = self.get_month_by_name(month_name)
            return month_info.start_timestamp, month_info.end_timestamp
        else:
            # Default to previous month (backward compatibility)
            available_months = self.get_available_months(count=1)
            if available_months:
                return available_months[0].start_timestamp, available_months[0].end_timestamp
            else:
                raise ValueError("No available months found")

    def list_available_months(self) -> List[Dict[str, str]]:
        """
        Get a simple list of available months for API responses

        Returns:
            List of dictionaries with month information
        """
        months = self.get_available_months()
        return [
            {
                "name": month.month_name,
                "display_name": month.display_name,
                "year": str(month.year),
                "month_number": str(month.month_number)
            }
            for month in months
        ]
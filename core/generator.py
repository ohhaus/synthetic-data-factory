import os

from dask.delayed import delayed
from dask.distributed import Client
import dask.dataframe as dd
from faker import Faker
import pandas as pd


class SyntheticDataGenerator:
    """Генератор синтетических данных с использованием Dask."""

    def __init__(self, num_rows, chunk_size=50_000, num_workers=4):
        """Инициализация генератора с указанными параметрами."""
        self.num_rows = num_rows
        self.chunk_size = chunk_size
        self.num_workers = num_workers
        self.output_dir = 'data'
        os.makedirs(self.output_dir, exist_ok=True)
        self.client = None

    @staticmethod
    def _generate_chunk(faker_seed, chunk_size, rows_remaining):
        """Генерация одного чанка синтетических данных."""
        fake = Faker()
        fake.seed_instance(faker_seed)
        actual_chunk_size = min(chunk_size, rows_remaining)
        data = [{
            'id': fake.uuid4(),
            'name': fake.name(),
            'birth_date': fake.date_of_birth(minimum_age=18, maximum_age=70),
            'passport': fake.passport_number(),
            'address': fake.address().replace("\n", ", "),
            'city': fake.city(),
            'country': fake.country(),
            'email': fake.email(),
            'bank_account': fake.iban(),
            'swift_code': fake.swift11(use_dataset=True, primary=True),
        } for _ in range(actual_chunk_size)]

        return pd.DataFrame(data)

    def generate_to_csv(self, output_file, records_per_file=None):
        """Генерация данных и сохранение их в CSV файл(ы)."""
        try:
            self.client = Client(n_workers=self.num_workers,
                                 threads_per_worker=1,
                                 dashboard_address=':0')

            output_base = os.path.splitext(output_file)[0]
            if output_base.endswith('.csv'):
                output_base = output_base[:-4]

            rows_remaining = self.num_rows
            chunks = []
            faker_seed = 0

            while rows_remaining > 0:
                chunk = delayed(self._generate_chunk)(
                    faker_seed, self.chunk_size, rows_remaining)
                chunks.append(chunk)
                rows_remaining -= self.chunk_size
                faker_seed += 1

            dask_df = dd.from_delayed(chunks)

            if records_per_file:
                num_partitions = max(1, self.num_rows // records_per_file)
                dask_df = dask_df.repartition(npartitions=num_partitions)
                filename_template = os.path.join(
                    self.output_dir, f"{output_base}_*.csv")
                dask_df.to_csv(
                    filename_template,
                    single_file=False,
                    index=False
                )

                file_paths = sorted([
                    os.path.join(self.output_dir, f)
                    for f in os.listdir(self.output_dir)
                    if f.startswith(f"{output_base}_") and f.endswith('.csv')
                ])
                return file_paths
            else:
                csv_path = os.path.join(self.output_dir, f"{output_base}.csv")
                dask_df.to_csv(csv_path, single_file=True, index=False)
                return [csv_path]

        finally:
            if self.client is not None:
                self.client.close()
                self.client = None

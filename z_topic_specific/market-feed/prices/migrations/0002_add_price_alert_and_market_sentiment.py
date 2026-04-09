from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('prices', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PriceAlert',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asset', models.CharField(max_length=20)),
                ('threshold', models.DecimalField(decimal_places=8, max_digits=20)),
                ('direction', models.CharField(choices=[('above', 'Above'), ('below', 'Below')], max_length=5)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'indexes': [models.Index(fields=['asset', 'is_active'], name='prices_pric_asset_a1b2c3_idx')],
            },
        ),
        migrations.CreateModel(
            name='MarketSentiment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asset', models.CharField(max_length=20)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('reddit_posts', models.JSONField()),
                ('analysis', models.TextField()),
            ],
            options={
                'indexes': [models.Index(fields=['asset', 'timestamp'], name='prices_mark_asset_d4e5f6_idx')],
            },
        ),
    ]

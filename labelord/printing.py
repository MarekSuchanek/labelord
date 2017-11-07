import click


class BasePrinter:
    SUCCESS_SUMMARY = '{} repo(s) updated successfully'
    ERROR_SUMMARY = '{} error(s) in total, please check log above'

    EVENT_CREATE = 'ADD'
    EVENT_DELETE = 'DEL'
    EVENT_UPDATE = 'UPD'
    EVENT_LABELS = 'LBL'

    RESULT_SUCCESS = 'SUC'
    RESULT_ERROR = 'ERR'
    RESULT_DRY = 'DRY'

    def __init__(self):
        self.repos = set()
        self.errors = 0

    def add_repo(self, slug):
        self.repos.add(slug)

    def event(self, event, result, repo, *args):
        if result == self.RESULT_ERROR:
            self.errors += 1

    def summary(self):
        pass

    def _create_summary(self):
        if self.errors > 0:
            return self.ERROR_SUMMARY.format(self.errors)
        return self.SUCCESS_SUMMARY.format(len(self.repos))


class Printer(BasePrinter):

    def event(self, event, result, repo, *args):
        super().event(event, result, repo, *args)
        if result == self.RESULT_ERROR:
            line_parts = ['ERROR: ' + event, repo, *args]
            click.echo('; '.join(line_parts))

    def summary(self):
        click.echo('SUMMARY: ' + self._create_summary())


class QuietPrinter(BasePrinter):
    pass


class VerbosePrinter(BasePrinter):

    LINE_START = '[{}][{}] {}'

    def event(self, event, result, repo, *args):
        super().event(event, result, repo, *args)
        line_parts = [self.LINE_START.format(event, result, repo), *args]
        click.echo('; '.join(line_parts))

    def summary(self):
        click.echo('[SUMMARY] ' + self._create_summary())

from labelord.printing import Printer, QuietPrinter
from labelord.github import GitHubError
from labelord.consts import DEFAULT_ERROR_RETURN, DEFAULT_SUCCESS_RETURN

class RunModes:

    @staticmethod
    def _make_labels_dict(labels_spec):
        return {k.lower(): (k, v) for k, v in labels_spec.items()}

    @classmethod
    def update_mode(cls, labels, labels_specs):
        create = dict()
        update = dict()
        xlabels = cls._make_labels_dict(labels)
        for name, color in labels_specs.items():
            if name.lower() not in xlabels:
                create[name] = (name, color)
            elif name not in labels:  # changed case of name
                old_name = xlabels[name.lower()][0]
                update[old_name] = (name, color)
            elif labels[name] != color:
                update[name] = (name, color)
        return create, update, dict()

    @classmethod
    def replace_mode(cls, labels, labels_specs):
        create, update, delete = cls.update_mode(labels, labels_specs)
        delete = {n: (n, c) for n, c in labels.items()
                  if n not in labels_specs}
        return create, update, delete


class RunProcessor:

    MODES = {
        'update': RunModes.update_mode,
        'replace': RunModes.replace_mode
    }

    def __init__(self, github, printer=None):
        self.github = github
        self.printer = printer or QuietPrinter()

    def _process_generic(self, slug, key, data, event, method):
        old_name, name, color = key, data[0], data[1]
        try:
            method(slug, name=name, color=color, old_name=old_name)
        except GitHubError as error:
            self.printer.event(event, Printer.RESULT_ERROR,
                               slug, name, color, error.code_message)
        else:
            self.printer.event(event, Printer.RESULT_SUCCESS,
                               slug, name, color)

    def _process_create(self, slug, key, data):
        self._process_generic(slug, key, data, Printer.EVENT_CREATE,
                              self.github.create_label)

    def _process_update(self, slug, key, data):
        self._process_generic(slug, key, data, Printer.EVENT_UPDATE,
                              self.github.update_label)

    def _process_delete(self, slug, key, data):
        self._process_generic(slug, key, data, Printer.EVENT_DELETE,
                              self.github.delete_label)

    @staticmethod
    def _process(slug, changes, processor):
        for key, data in changes.items():
            processor(slug, key, data)

    def _run_one(self, slug, labels_specs, mode):
        self.printer.add_repo(slug)
        try:
            labels = self.github.list_labels(slug)
        except GitHubError as error:
            self.printer.event(Printer.EVENT_LABELS, Printer.RESULT_ERROR,
                               slug, error.code_message)
        else:
            create, update, delete = mode(labels, labels_specs)
            self._process(slug, create, self._process_create)
            self._process(slug, update, self._process_update)
            self._process(slug, delete, self._process_delete)

    def run(self, slugs, labels_specs, mode):
        for slug in slugs:
            self._run_one(slug, labels_specs, mode)
        self.printer.summary()
        return (DEFAULT_ERROR_RETURN if self.printer.errors > 0
                else DEFAULT_SUCCESS_RETURN)


class DryRunProcessor(RunProcessor):

    def __init__(self, github, printer=None):
        super().__init__(github, printer)

    def _process_create(self, slug, key, data):
        self.printer.event(Printer.EVENT_CREATE, Printer.RESULT_DRY,
                           slug, data[0], data[1])

    def _process_update(self, slug, key, data):
        self.printer.event(Printer.EVENT_UPDATE, Printer.RESULT_DRY,
                           slug, data[0], data[1])

    def _process_delete(self, slug, key, data):
        self.printer.event(Printer.EVENT_DELETE, Printer.RESULT_DRY,
                           slug, data[0], data[1])

from .. s2g_logging import Survey2GISLogger


class LogTab:
    def __init__(self, parent_widget):
        """Access main widget for shared variables and settings."""
        self.parent_widget = parent_widget
        self.logger = Survey2GISLogger(parent_widget)        
        self.connect_signals()

    def connect_signals(self):
        # reest logs 
        self.parent_widget.reset_logs_button.clicked.connect(self.reset_logs)        
    
    def reset_logs(self):
        self.parent_widget.output_log.setText("")
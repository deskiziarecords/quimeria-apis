# dashboard/smk_tui_command_center.py — ADAPTED from eToro TUI
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, DataTable, Sparkline, Log
from textual.reactive import reactive
import asyncio

class SMKCommandCenter(App):
    """
    Terminal UI for SMK — low-latency, keyboard-driven.
    
    For traders who need sub-second updates without browser overhead.
    Runs in tmux/screen alongside execution terminals.
    """
    
    CSS = """
    Screen { align: center middle; }
    #main { layout: grid; grid-size: 3 2; }
    .panel { border: solid green; padding: 1; }
    .alert { border: solid red; }
    .warning { border: solid yellow; }
    """
    
    # Reactive data (auto-updates UI)
    equity = reactive(0.0)
    open_pnl = reactive(0.0)
    mandra_delta_e = reactive(0.0)
    hmm_regime = reactive("UNKNOWN")
    lambda_states = reactive({})
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Container(id="main"):
            # Row 1: KPIs
            with Vertical(id="kpis", classes="panel"):
                yield Static("SOVEREIGN CAPITAL", id="title")
                yield Static("Equity: $0", id="equity")
                yield Static("Open PnL: $0", id="pnl")
                yield Static("Daily: $0", id="daily")
                yield Sparkline([], id="equity_curve")
            
            # Row 1: Regime State
            with Vertical(id="regime", classes="panel"):
                yield Static("REGIME", id="regime_title")
                yield Static("HMM: UNKNOWN", id="hmm_state")
                yield Static("Mandra: 0.0000", id="mandra")
                yield Static("Consciousness: 0.00", id="consciousness")
                yield Static("Temperature: 0.00", id="blackbody")
            
            # Row 1: Lambda Array
            with Vertical(id="lambdas", classes="panel"):
                yield Static("λ SENSORS", id="lambda_title")
                yield DataTable(id="lambda_table")
            
            # Row 2: Positions
            with Vertical(id="positions", classes="panel"):
                yield Static("POSITIONS", id="pos_title")
                yield DataTable(id="position_table")
            
            # Row 2: Execution Log
            with Vertical(id="execution", classes="panel"):
                yield Static("EXECUTION", id="exec_title")
                yield Log(id="exec_log", max_lines=100)
            
            # Row 2: Alerts
            with Vertical(id="alerts", classes="panel alert"):
                yield Static("ALERTS", id="alert_title")
                yield Log(id="alert_log", max_lines=50)
        
        yield Footer()
    
    def on_mount(self):
        """Initialize tables and start refresh loop"""
        # Lambda sensor table
        table = self.query_one("#lambda_table", DataTable)
        table.add_columns("Sensor", "State", "Value", "Confidence")
        for i in range(1, 9):
            table.add_row(f"λ{i}", "NEUTRAL", "0.000", "0.00")
        
        # Position table
        pos_table = self.query_one("#position_table", DataTable)
        pos_table.add_columns("Instrument", "Side", "Size", "Entry", "PnL", "ΔE")
        
        # Start refresh loop
        self.set_interval(0.5, self.refresh_data)  # 500ms refresh
    
    async def refresh_data(self):
        """Pull from SMK kernel and update UI"""
        # In production: ZMQ pull from smk_data_bus
        data = await self._fetch_from_kernel()
        
        self.equity = data.get('equity', 0)
        self.open_pnl = data.get('open_pnl', 0)
        self.mandra_delta_e = data.get('mandra_delta_e', 0)
        self.hmm_regime = data.get('hmm_regime', 'UNKNOWN')
        self.lambda_states = data.get('lambda_states', {})
        
        self._update_ui()
    
    def _update_ui(self):
        """Update all widgets with current data"""
        # KPIs
        self.query_one("#equity", Static).update(f"Equity: ${self.equity:,.0f}")
        self.query_one("#pnl", Static).update(f"Open PnL: ${self.open_pnl:,.0f}")
        
        # Regime
        regime_color = "green" if self.hmm_regime in ["BULL", "BEAR"] else "yellow"
        self.query_one("#hmm_state", Static).update(f"HMM: [{regime_color}]{self.hmm_regime}")
        
        mandra_color = "green" if self.mandra_delta_e > 0.02 else "red"
        self.query_one("#mandra", Static).update(f"Mandra: [{mandra_color}]{self.mandra_delta_e:.4f}")
        
        # Lambda sensors
        table = self.query_one("#lambda_table", DataTable)
        table.clear()
        for sensor_id, state in self.lambda_states.items():
            color = "green" if state['stance'] == "BULLISH" else "red" if state['stance'] == "BEARISH" else "white"
            table.add_row(
                sensor_id,
                f"[{color}]{state['stance']}",
                f"{state['value']:.3f}",
                f"{state['confidence']:.2f}"
            )
        
        # Check alerts
        if self.mandra_delta_e < 0.02 and self.hmm_regime != "SIDEWAYS":
            self.query_one("#alerts", Container).add_class("alert")
            self.query_one("#alert_log", Log).write_line(
                f"ALERT: Mandra veto at ΔE={self.mandra_delta_e:.4f}"
            )
    
    async def _fetch_from_kernel(self) -> dict:
        """Fetch from SMK ZMQ data bus"""
        # Placeholder — integrate with your zmq_data_bus.py
        return {
            'equity': 1000000,
            'open_pnl': 15000,
            'mandra_delta_e': 0.025,
            'hmm_regime': 'BULL',
            'lambda_states': {
                'λ1': {'stance': 'BULLISH', 'value': 0.65, 'confidence': 0.85},
                'λ3': {'stance': 'NEUTRAL', 'value': 0.12, 'confidence': 0.60},
                'λ7': {'stance': 'BULLISH', 'value': 0.88, 'confidence': 0.92},
            }
        }
    
    def action_refresh(self):
        """Manual refresh on 'r' key"""
        asyncio.create_task(self.refresh_data())
    
    def action_kill_switch(self):
        """Emergency halt on 'k' key"""
        # Trigger λ8 kill switch
        self.query_one("#alert_log", Log).write_line("KILL SWITCH ACTIVATED")
        # Send halt signal to SMK kernel
    
    def action_toggle_panel(self, panel_id: str):
        """Numeric hotkeys for panels"""
        # 1=KPIs, 2=Regime, 3=Lambdas, etc.
        pass


# Run: python -m dashboard.smk_tui_command_center
if __name__ == "__main__":
    app = SMKCommandCenter()
    app.run()

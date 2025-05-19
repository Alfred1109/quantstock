/**
 * Chart.js日期适配器修复脚本
 * 解决"locale must contain localize property"错误
 */
(function() {
    // 创建一个简单的locale对象
    const zhCNLocale = {
        code: 'zh-CN',
        formatLong: {
            date: {
                full: 'yyyy年MM月dd日',
                long: 'yyyy年MM月dd日',
                medium: 'yyyy-MM-dd',
                short: 'yyyy-MM-dd'
            },
            time: {
                full: 'HH:mm:ss',
                long: 'HH:mm:ss',
                medium: 'HH:mm:ss',
                short: 'HH:mm'
            },
            dateTime: {
                full: 'yyyy年MM月dd日 HH:mm:ss',
                long: 'yyyy年MM月dd日 HH:mm:ss',
                medium: 'yyyy-MM-dd HH:mm:ss',
                short: 'yyyy-MM-dd HH:mm'
            }
        },
        // 添加必要的localize方法
        localize: {
            ordinalNumber: function(n) {
                return n.toString();
            },
            era: function(value) {
                return value === 0 ? '公元前' : '公元';
            },
            quarter: function(quarter) {
                return ['第一季度', '第二季度', '第三季度', '第四季度'][quarter - 1];
            },
            month: function(month) {
                return ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月'][month];
            },
            day: function(day) {
                return ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'][day];
            },
            dayPeriod: function(dayPeriod) {
                return dayPeriod === 'am' ? '上午' : '下午';
            }
        },
        // 添加必要的match方法
        match: {
            ordinalNumber: () => ({ value: 0, rest: '' }),
            era: () => ({ value: 0, rest: '' }),
            quarter: () => ({ value: 0, rest: '' }),
            month: () => ({ value: 0, rest: '' }),
            day: () => ({ value: 0, rest: '' }),
            dayPeriod: () => ({ value: 0, rest: '' })
        },
        options: {
            weekStartsOn: 1,
            firstWeekContainsDate: 4
        }
    };

    // 修复Chart.js的配置函数
    window.fixChartConfig = function(chartConfig) {
        // 移除adapters.date.locale配置
        if (chartConfig && chartConfig.options && chartConfig.options.scales && chartConfig.options.scales.x) {
            // 移除失效的locale配置
            if (chartConfig.options.scales.x.adapters && chartConfig.options.scales.x.adapters.date) {
                delete chartConfig.options.scales.x.adapters.date.locale;
            }
            
            // 可选：完全移除adapters配置
            if (chartConfig.options.scales.x.adapters) {
                delete chartConfig.options.scales.x.adapters;
            }
            
            // 简化time配置
            if (chartConfig.options.scales.x.time) {
                chartConfig.options.scales.x.time = {
                    unit: chartConfig.options.scales.x.time.unit || 'day',
                    displayFormats: {
                        day: 'MM/dd',
                        week: 'MM/dd',
                        month: 'yyyy/MM'
                    }
                };
            }
        }
        
        return chartConfig;
    };
    
    // 设置全局Chart.js配置
    window.addEventListener('DOMContentLoaded', function() {
        // 尝试多种方式覆盖Chart.js的locale处理
        if (window.Chart) {
            try {
                // 方法1: 直接设置全局默认值
                if (window.Chart.defaults && window.Chart.defaults.scales && window.Chart.defaults.scales.time) {
                    delete window.Chart.defaults.scales.time.adapters;
                }
                
                // 方法2: 替换适配器方法
                if (window._adapters && window._adapters._date) {
                    window._adapters._date.prototype._create = function(time) {
                        return new Date(time);
                    };
                }
                
                // 方法3: 提供全局locale对象
                if (window.dateFns) {
                    window.dateFns.locale = zhCNLocale;
                }
                
                console.log('Chart.js配置修复已应用');
            } catch (e) {
                console.error('Chart.js配置修复失败:', e);
            }
        }
    });
})(); 
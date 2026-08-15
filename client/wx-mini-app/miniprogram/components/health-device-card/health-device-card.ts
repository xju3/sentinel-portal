Component({
  properties: {
    item: {
      type: Object,
      value: {},
    },
  },
  methods: {
    onTap() {
      this.triggerEvent('click', this.data.item)
    },
  },
})
